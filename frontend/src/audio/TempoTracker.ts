/** Tracks BPM from onset events with rate-limited smoothing and catchup. */
export class TempoTracker {
  private onsetHistory: number[] = []; // timestamps in ms, max 16
  private readonly HISTORY_MAX = 16;

  private estimatedBpm = 100;
  private appliedBpm = 100;
  private lastApplyMs = 0;
  private readonly APPLY_INTERVAL_MS = 500;
  private readonly MAX_RATE_PER_SEC = 0.08; // ±8% per second
  private readonly CATCHUP_THRESHOLD = 0.30; // 30% divergence
  private catchupStreak = 0;

  onBpmChange?: (bpm: number) => void;

  reset(initialBpm: number): void {
    this.onsetHistory = [];
    this.estimatedBpm = initialBpm;
    this.appliedBpm = initialBpm;
    this.lastApplyMs = 0;
    this.catchupStreak = 0;
  }

  handleOnset(timeMs: number): void {
    this.onsetHistory.push(timeMs);
    if (this.onsetHistory.length > this.HISTORY_MAX) this.onsetHistory.shift();
    if (this.onsetHistory.length < 4) return;

    const estimated = this.estimateFromHistory();
    if (estimated === null) return;

    this.estimatedBpm = estimated;
    this.maybeApply(timeMs);
  }

  private estimateFromHistory(): number | null {
    const h = this.onsetHistory;
    if (h.length < 4) return null;

    // Use median of adjacent inter-onset intervals
    const iois: number[] = [];
    for (let i = 1; i < h.length; i++) iois.push(h[i] - h[i - 1]);

    // Filter out implausible IOIs (< 150ms = >400 BPM, > 2000ms = <30 BPM)
    const valid = iois.filter((d) => d >= 150 && d <= 2000);
    if (valid.length < 2) return null;

    const sorted = [...valid].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];

    const bpm = 60000 / median;
    if (bpm < 30 || bpm > 300) return null;
    return bpm;
  }

  private maybeApply(nowMs: number): void {
    const elapsed = nowMs - this.lastApplyMs;
    if (elapsed < this.APPLY_INTERVAL_MS) return;
    this.lastApplyMs = nowMs;

    const divergence = Math.abs(this.estimatedBpm - this.appliedBpm) / this.appliedBpm;

    if (divergence > this.CATCHUP_THRESHOLD) {
      this.catchupStreak++;
      if (this.catchupStreak >= 2) {
        // Immediate jump for large sustained divergence (fermata / ritenuto)
        this.appliedBpm = this.estimatedBpm;
        this.catchupStreak = 0;
        this.onBpmChange?.(Math.round(this.appliedBpm));
        return;
      }
    } else {
      this.catchupStreak = 0;
    }

    // Rate-limited smooth approach
    const maxDelta = this.appliedBpm * this.MAX_RATE_PER_SEC * (elapsed / 1000);
    const target = this.estimatedBpm;
    this.appliedBpm = clamp(target, this.appliedBpm - maxDelta, this.appliedBpm + maxDelta);
    this.onBpmChange?.(Math.round(this.appliedBpm));
  }

  get currentAppliedBpm(): number { return this.appliedBpm; }
  get currentEstimatedBpm(): number { return this.estimatedBpm; }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
