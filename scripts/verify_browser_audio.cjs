const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const out = process.argv[2];
fs.mkdirSync(out, { recursive: true });
let page, browser;
(async () => {
  browser = await chromium.launch({ args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required"] });
  const context = await browser.newContext({
    viewport: { width: 412, height: 915 },
    userAgent: "Mozilla/5.0 IMSLPAccompanistAndroid/0.2.5",
    ignoreHTTPSErrors: true,
  });
  await context.addInitScript(() => {
    localStorage.setItem("lang", "en");
    localStorage.setItem("imslp-accompanist.omr-server.v1", JSON.stringify({
      serverUrl: "http://127.0.0.1:18765", apiToken: "integration-test-token", omrEngine: "hybrid",
    }));
    window.__audioMeters = [];
    window.__audioFrames = [];
    const original = AudioNode.prototype.connect;
    AudioNode.prototype.connect = function(destination, ...args) {
      if (destination instanceof AudioDestinationNode && !this.__meterAttached) {
        this.__meterAttached = true;
        const meter = this.context.createAnalyser();
        meter.fftSize = 2048;
        const silent = this.context.createGain();
        silent.gain.value = 0;
        original.call(this, meter);
        original.call(meter, silent);
        original.call(silent, destination);
        window.__audioMeters.push(meter);
      }
      return original.call(this, destination, ...args);
    };
    setInterval(() => {
      let rms = 0, peak = 0;
      for (const meter of window.__audioMeters) {
        const data = new Float32Array(meter.fftSize);
        meter.getFloatTimeDomainData(data);
        const value = Math.sqrt(data.reduce((sum, x) => sum + x*x, 0) / data.length);
        rms = Math.max(rms, value);
        for (const x of data) peak = Math.max(peak, Math.abs(x));
      }
      window.__audioFrames.push({ time: performance.now(), rms, peak });
    }, 25);
  });
  page = await context.newPage();
  page.setDefaultTimeout(20000);
  const errors = [], samples = new Set(), checks = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("response", r => { if (r.url().includes("/audio/salamander/") && r.ok()) samples.add(r.url()); });
  await page.goto(process.env.UI_URL || "http://127.0.0.1:5173");
  await page.waitForSelector(".app--android");
  const waitAnalyze = () => page.waitForResponse(r => r.url().endsWith("/analyze") && r.request().method() === "POST");
  let response = waitAnalyze();
  await page.locator('input[type=file]').first().setInputFiles(path.join(out, "replay.pdf"));
  const result = await (await response).json();
  assert.equal(result.omr_engine, "hybrid");
  assert(result.warnings.some(w => w.includes("25小節 / 170音 (81.3%)")));
  await page.locator(".mobile-score-tab").filter({ hasText: "Score" }).click();
  await page.waitForSelector(".score-area svg", { timeout: 60000 });
  checks.push("real-api-hybrid-score-render");
  await page.screenshot({ path: path.join(out, "hybrid-real-api.png"), fullPage: true });

  await page.locator(".mobile-topbar__back").click();
  response = waitAnalyze();
  await page.locator('input[type=file]').first().setInputFiles(path.join(out, "audio.musicxml"));
  const audio = await (await response).json();
  assert.equal(audio.omr_engine, null);
  await page.locator(".mobile-score-tab").filter({ hasText: "Score" }).click();
  await page.waitForSelector(".score-area svg");
  await page.locator(".mobile-more").click();
  const tempo = page.locator('.mobile-stepper input[type=range]');
  const setTempo = bpm => tempo.evaluate((input, value) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(value));
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, bpm);
  await page.locator(".mobile-settings-grid select").selectOption("0");
  const metro = page.locator(".mobile-toggle").filter({ hasText: "Metronome" });
  if ((await metro.getAttribute("class")).includes("--on")) await metro.click();
  const play = page.locator(".mobile-play");
  const stopped = () => page.waitForFunction(() => !document.querySelector(".mobile-play--stop"));
  await setTempo(240);
  await play.click();
  await page.waitForSelector(".mobile-play--stop", { timeout: 60000 });
  const start = Date.now();
  await page.waitForFunction(() => window.__audioFrames.some(f => f.rms > 0.0001));
  await stopped();
  const duration = Date.now() - start;
  assert(duration > 1300 && duration < 3500, "completion duration " + duration);
  assert(samples.size > 0, "Real Salamander samples were not downloaded");
  checks.push("sample-audio-non-silent", "non-loop-completion");
  await setTempo(120);
  await play.click();
  await page.waitForSelector(".mobile-play--stop");
  await page.waitForTimeout(550);
  await setTempo(240);
  await stopped();
  checks.push("live-tempo-change");

  const loop = page.locator(".mobile-toggle").filter({ hasText: "Loop" });
  await loop.click();
  await setTempo(240);
  await play.click();
  await page.waitForSelector(".mobile-play--stop");
  await page.waitForTimeout(4600);
  assert((await play.getAttribute("class")).includes("--stop"));
  await play.click();
  await stopped();
  checks.push("two-loop-ranges-and-stop");
  await loop.click();
  await page.waitForTimeout(1200);
  await setTempo(30);
  await play.click();
  await page.waitForSelector(".mobile-play--stop");
  await page.waitForTimeout(600);
  await play.click();
  await page.waitForTimeout(1400);
  const frames = await page.evaluate(() => window.__audioFrames);
  assert(Math.max(...frames.slice(-12).map(f => f.rms)) < 0.0001, "Stop left sustained piano audio sounding");
  checks.push("stop-silences-long-piano-note");
  assert.deepEqual(errors, []);
  await page.screenshot({ path: path.join(out, "audio-controls.png"), fullPage: true });
  fs.writeFileSync(path.join(out, "audio-waveform.json"), JSON.stringify(frames));
  fs.writeFileSync(path.join(out, "browser-verification.json"), JSON.stringify({
    passed: true, checks, samples: [...samples], duration_ms: duration,
    peak: Math.max(...frames.map(f => f.peak)), errors,
  }, null, 2));
  console.log("Real API, score rendering and Web Audio controls passed.");
  await browser.close();
})().catch(async error => {
  console.error(error);
  if (page) {
    await page.screenshot({ path: path.join(out, "failure.png"), fullPage: true }).catch(() => {});
    fs.writeFileSync(path.join(out, "failure-ui.txt"), await page.locator("body").innerText().catch(() => ""));
    fs.writeFileSync(path.join(out, "audio-waveform.json"), JSON.stringify(await page.evaluate(() => window.__audioFrames).catch(() => [])));
  }
  fs.writeFileSync(path.join(out, "browser-verification.json"), JSON.stringify({ passed: false, error: String(error) }));
  if (browser) await browser.close();
  process.exit(1);
});
