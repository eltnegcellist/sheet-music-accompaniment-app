export interface LevelDetail {
  rmsDb: number;
  noiseFloorDb: number;
  silenceThresholdDb: number;
  onsetThresholdDb: number;
}

/** Real-time microphone analysis: noise floor, silence/activity, onsets, pitch. */
export class AudioAnalyzer {
  private stream: MediaStream | null = null;
  private audioCtx: AudioContext | null = null;
  private analyserNode: AnalyserNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private filterNode: BiquadFilterNode | null = null;
  private rafId: number | null = null;

  // Sliding-minimum noise floor (3 s of 20 ms frames = 150 samples)
  private rmsHistory: number[] = [];
  private readonly RMS_HISTORY_MAX = 150;
  private noiseFloorDb = -55;

  // Silence / activity hysteresis
  private silenceTimerId: ReturnType<typeof setTimeout> | null = null;
  private readonly SILENCE_HOLD_MS = 3000;
  // Start assuming active so silence is detectable immediately without
  // requiring a prior onset event.
  private currentlyActive = true;

  // Onset detection
  private lastOnsetMs = 0;
  private readonly ONSET_COOLDOWN_MS = 80;
  private prevRmsDb = -60;

  // Pitch (autocorrelation)
  private pitchBuf: Float32Array<ArrayBuffer> | null = null;

  onOnset?: (timeMs: number) => void;
  onSilence?: () => void;
  onActivity?: () => void;
  onPitch?: (hz: number | null) => void;
  onLevel?: (rmsDb: number) => void;
  onLevelDetail?: (detail: LevelDetail) => void;

  get isRunning(): boolean {
    return this.rafId !== null;
  }

  async start(): Promise<void> {
    // Music-aware constraints: enable AEC to reduce speaker feedback,
    // disable noise suppression and AGC which would distort musical content
    // and compress dynamics needed for onset detection.
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: false,
        autoGainControl: false,
      },
      video: false,
    });
    this.audioCtx = new AudioContext();
    this.sourceNode = this.audioCtx.createMediaStreamSource(this.stream);

    this.filterNode = this.audioCtx.createBiquadFilter();
    this.filterNode.type = "highpass";
    this.filterNode.frequency.value = 80;

    this.analyserNode = this.audioCtx.createAnalyser();
    this.analyserNode.fftSize = 2048;
    this.analyserNode.smoothingTimeConstant = 0;

    this.sourceNode.connect(this.filterNode);
    this.filterNode.connect(this.analyserNode);

    this.pitchBuf = new Float32Array(this.analyserNode.fftSize) as Float32Array<ArrayBuffer>;
    this.rafId = requestAnimationFrame(this.tick);
  }

  stop(): void {
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    if (this.silenceTimerId !== null) {
      clearTimeout(this.silenceTimerId);
      this.silenceTimerId = null;
    }
    this.sourceNode?.disconnect();
    this.filterNode?.disconnect();
    this.analyserNode?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.audioCtx?.close().catch(() => {});
    this.stream = null;
    this.audioCtx = null;
    this.sourceNode = null;
    this.filterNode = null;
    this.analyserNode = null;
    this.rmsHistory = [];
    this.currentlyActive = true;
    this.prevRmsDb = -60;
    this.lastOnsetMs = 0;
  }

  private tick = (): void => {
    if (!this.analyserNode || !this.pitchBuf) return;
    this.rafId = requestAnimationFrame(this.tick);

    this.analyserNode.getFloatTimeDomainData(this.pitchBuf);

    const rmsDb = this.computeRmsDb(this.pitchBuf);
    this.updateNoiseFloor(rmsDb);
    this.onLevel?.(rmsDb);

    const silenceThresholdDb = this.noiseFloorDb + 10;
    const onsetThresholdDb = this.noiseFloorDb + 15;
    this.onLevelDetail?.({ rmsDb, noiseFloorDb: this.noiseFloorDb, silenceThresholdDb, onsetThresholdDb });

    this.handleSilenceActivity(rmsDb, silenceThresholdDb);
    this.handleOnset(rmsDb, onsetThresholdDb);

    const hz = this.currentlyActive ? this.detectPitch(this.pitchBuf) : null;
    this.onPitch?.(hz);

    this.prevRmsDb = rmsDb;
  };

  private computeRmsDb(buf: Float32Array): number {
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    const rms = Math.sqrt(sum / buf.length);
    return rms < 1e-9 ? -90 : 20 * Math.log10(rms);
  }

  updateNoiseFloor(rmsDb: number): void {
    this.rmsHistory.push(rmsDb);
    if (this.rmsHistory.length > this.RMS_HISTORY_MAX) this.rmsHistory.shift();
    const min = Math.min(...this.rmsHistory);
    this.noiseFloorDb = min + 6;
  }

  /** Exposed for testing: compute sliding min noise floor from an array of dB values. */
  computeNoiseFloor(samples: number[]): number {
    if (samples.length === 0) return -55;
    return Math.min(...samples) + 6;
  }

  private handleSilenceActivity(rmsDb: number, silenceThresholdDb: number): void {
    const isSilent = rmsDb < silenceThresholdDb;
    if (!isSilent) {
      // Sound present: cancel any pending silence timer
      if (this.silenceTimerId !== null) {
        clearTimeout(this.silenceTimerId);
        this.silenceTimerId = null;
      }
      if (!this.currentlyActive) {
        this.currentlyActive = true;
        this.onActivity?.();
      }
    } else {
      // Silence: start hold timer if not already counting down
      if (this.currentlyActive && this.silenceTimerId === null) {
        this.silenceTimerId = setTimeout(() => {
          this.silenceTimerId = null;
          this.currentlyActive = false;
          this.onSilence?.();
        }, this.SILENCE_HOLD_MS);
      }
    }
  }

  private handleOnset(rmsDb: number, onsetThresholdDb: number): void {
    if (!this.onOnset) return;
    const now = performance.now();
    if (
      rmsDb > onsetThresholdDb &&
      rmsDb > this.prevRmsDb + 3 && // rising edge
      now - this.lastOnsetMs > this.ONSET_COOLDOWN_MS
    ) {
      this.lastOnsetMs = now;
      this.onOnset(now);
    }
  }

  /** Autocorrelation pitch detection with octave correction.
   *  Returns fundamental frequency in Hz, or null if unreliable. */
  detectPitch(buf: Float32Array, sampleRate?: number): number | null {
    const rate = sampleRate ?? this.audioCtx?.sampleRate ?? 44100;
    const n = buf.length;
    const minLag = Math.floor(rate / 2000); // ~2000 Hz max
    const maxLag = Math.floor(rate / 60);   // ~60 Hz min

    let bestLag = -1;
    let bestVal = -Infinity;

    // Normalized autocorrelation
    let r0 = 0;
    for (let i = 0; i < n; i++) r0 += buf[i] * buf[i];
    if (r0 < 1e-6) return null;

    for (let lag = minLag; lag <= maxLag && lag < n; lag++) {
      let r = 0;
      for (let i = 0; i < n - lag; i++) r += buf[i] * buf[i + lag];
      const normalized = r / r0;
      if (normalized > bestVal) {
        bestVal = normalized;
        bestLag = lag;
      }
    }

    if (bestLag < 0 || bestVal < 0.4) return null;

    let hz = rate / bestLag;

    // Octave correction: halve/double if we're likely off by an octave
    // Typical solo instrument range: 60 Hz (C2) to 2000 Hz (C7 ish)
    if (hz > 1500 && bestLag * 2 <= maxLag) {
      const r2 = this.autocorr(buf, bestLag * 2) / r0;
      if (r2 > bestVal * 0.8) hz /= 2;
    } else if (hz < 80 && bestLag / 2 >= minLag) {
      const r2 = this.autocorr(buf, Math.round(bestLag / 2)) / r0;
      if (r2 > bestVal * 0.8) hz *= 2;
    }

    return hz;
  }

  private autocorr(buf: Float32Array, lag: number): number {
    let r = 0;
    for (let i = 0; i < buf.length - lag; i++) r += buf[i] * buf[i + lag];
    return r;
  }

  // Expose for testing
  get _noiseFloorDb(): number { return this.noiseFloorDb; }
  get _currentlyActive(): boolean { return this.currentlyActive; }
  get _rmsHistory(): number[] { return [...this.rmsHistory]; }
}
