import { describe, expect, it } from "vitest";
import { AudioAnalyzer } from "../AudioAnalyzer";

describe("AudioAnalyzer", () => {
  describe("computeNoiseFloor", () => {
    it("returns min + 6 from samples", () => {
      const analyzer = new AudioAnalyzer();
      expect(analyzer.computeNoiseFloor([-60, -50, -40])).toBeCloseTo(-60 + 6);
    });

    it("returns -55 for empty array", () => {
      const analyzer = new AudioAnalyzer();
      expect(analyzer.computeNoiseFloor([])).toBe(-55);
    });

    it("adapts to a single sample", () => {
      const analyzer = new AudioAnalyzer();
      expect(analyzer.computeNoiseFloor([-30])).toBeCloseTo(-30 + 6);
    });
  });

  describe("updateNoiseFloor", () => {
    it("slides over old samples beyond 150", () => {
      const analyzer = new AudioAnalyzer();
      // Fill 150 samples at -60 dB
      for (let i = 0; i < 150; i++) analyzer.updateNoiseFloor(-60);
      expect(analyzer._noiseFloorDb).toBeCloseTo(-60 + 6);

      // Push 150 louder samples — old -60 samples should evict
      for (let i = 0; i < 150; i++) analyzer.updateNoiseFloor(-30);
      expect(analyzer._noiseFloorDb).toBeCloseTo(-30 + 6);
    });
  });

  describe("detectPitch", () => {
    const sampleRate = 44100;

    function sineWave(hz: number, n: number): Float32Array<ArrayBuffer> {
      const buf = new Float32Array(n) as Float32Array<ArrayBuffer>;
      for (let i = 0; i < n; i++) {
        buf[i] = Math.sin((2 * Math.PI * hz * i) / sampleRate);
      }
      return buf;
    }

    it("detects A4 (440 Hz)", () => {
      const analyzer = new AudioAnalyzer();
      const buf = sineWave(440, 2048);
      const hz = analyzer.detectPitch(buf, sampleRate);
      expect(hz).not.toBeNull();
      expect(hz!).toBeGreaterThan(420);
      expect(hz!).toBeLessThan(460);
    });

    it("detects G3 (~196 Hz)", () => {
      const analyzer = new AudioAnalyzer();
      const buf = sineWave(196, 2048);
      const hz = analyzer.detectPitch(buf, sampleRate);
      expect(hz).not.toBeNull();
      expect(hz!).toBeGreaterThan(180);
      expect(hz!).toBeLessThan(210);
    });

    it("returns null for silent buffer", () => {
      const analyzer = new AudioAnalyzer();
      const buf = new Float32Array(2048) as Float32Array<ArrayBuffer>;
      expect(analyzer.detectPitch(buf, sampleRate)).toBeNull();
    });
  });
});
