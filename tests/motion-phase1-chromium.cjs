#!/usr/bin/env node
/**
 * Actual Chromium browser smoke test for motion Phase-1.
 * No student videos; use two synthetic WebM files prepared by ffmpeg in CI.
 * CDN requests are blocked intentionally to exercise missing model fallback.
 * Does NOT validate ChromeOS, Safari, a real MoveNet detector, or frame precision.
 */
const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

const bin = process.env.BROWSER_BIN || '/usr/bin/google-chrome';
const htmlPath = path.resolve(__dirname, '..', 'index.html');
const demo1 = path.resolve(__dirname, 'fixtures', 'motion-test-a.webm');
const demo2 = path.resolve(__dirname, 'fixtures', 'motion-test-b.webm');

function expectNear(actual, expected, tolerance = 0.12) {
  assert.ok(Math.abs(actual - expected) <= tolerance, 'expected near ' + expected + ', got ' + actual);
}
async function main() {
  for (const file of [htmlPath, demo1, demo2]) {
    assert.ok(fs.existsSync(file), 'missing fixture: ' + file);
  }
  const browser = await chromium.launch({
    headless: true,
    executablePath: bin,
    args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required', '--disable-dev-shm-usage'],
  });
  const passed = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 800 } });
    const browserErrors = [];
    page.on('pageerror', error => browserErrors.push(error.message));
    const unexpectedRequests = [];
    page.on('request', request => {
      if (/^https?:/.test(request.url()) && !request.url().startsWith('https://cdn.jsdelivr.net/')) {
        unexpectedRequests.push(request.url());
      }
    });
    await page.addInitScript(() => {
      window.__revoked = [];
      const original = URL.revokeObjectURL;
      URL.revokeObjectURL = function (value) {
        window.__revoked.push(value);
        return original.call(this, value);
      };
    });
    await page.route('https://cdn.jsdelivr.net/**', route => route.abort('failed'));

    // Run actual HTML and actual video player implementation, not mocked DOM.
    await page.goto('file://' + htmlPath, { waitUntil: 'load' });
    await page.waitForFunction(() => document.querySelector('.status')?.textContent?.includes('姿勢モデルを読み込めません'));
    assert.equal(await page.locator('video').count(), 1);
    assert.equal(await page.locator('canvas').count(), 1);
    passed.push('B1: CDN blocked, real Chrome initializes controls and Japanese model warning');

    await page.locator('input[type="file"]').setInputFiles(demo1);
    await page.waitForFunction(() => {
      const video = document.querySelector('video');
      return video.readyState >= 2 && video.videoWidth > 0 && video.duration > 0;
    }, { timeout: 12000 });
    await page.waitForFunction(() => document.querySelector('video').currentTime > 0.15, { timeout: 10000 });
    passed.push('B2: synthetic WebM local file plays in Chromium without pose model');

    // A transparent canvas is VALID when the video beneath it is visible.
    // Check actual composite pixels from the browser screenshot, not canvas alone.
    await page.waitForTimeout(200);
    const screenshot = await page.locator('.video-wrapper').screenshot({
      path: path.resolve(__dirname, 'fixtures', 'browser-fallback.png'),
    });
    const pixels = await page.evaluate(async (base64) => {
      const img = new Image();
      img.src = 'data:image/png;base64,' + base64;
      await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; });
      const surface = document.createElement('canvas');
      surface.width = img.naturalWidth;
      surface.height = img.naturalHeight;
      const ctx = surface.getContext('2d');
      ctx.drawImage(img, 0, 0);
      return Array.from(ctx.getImageData(
        Math.floor(surface.width / 2), Math.floor(surface.height / 2), 1, 1,
      ).data);
    }, screenshot.toString('base64'));
    assert.ok(pixels[0] > 80 && pixels[0] > pixels[1] + 40,
      'actual composite screenshot is not visibly red video: ' + pixels);
    const warning = await page.locator('.status').innerText();
    assert.match(warning, /姿勢モデル/);
    passed.push('B3: actual Chromium screenshot displays red video and preserves model warning');

    await page.locator('.playpause').click();
    assert.equal(await page.locator('video').evaluate(v => v.paused), true);
    await page.locator('.playpause').click();
    await page.waitForFunction(() => !document.querySelector('video').paused);
    passed.push('B4: play and pause buttons control real video');

    await page.locator('.speed').selectOption('1.5');
    const rate = await page.locator('video').evaluate(v => v.playbackRate);
    expectNear(rate, 1.5, 0.01);
    passed.push('B5: playback speed selection changes actual playbackRate');

    await page.locator('.flipBtn').click();
    const flip = await page.locator('video').evaluate(v => v.style.transform);
    assert.equal(flip, 'scaleX(-1)');
    passed.push('B6: flip button applies mirror transform');

    await page.locator('.playpause').click();
    assert.equal(await page.locator('video').evaluate(v => v.paused), true);
    await page.locator('.seek').evaluate(el => {
      el.value = '0.8';
      el.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await page.waitForFunction(() => document.querySelector('video').currentTime >= 0.7);
    const seekTime = await page.locator('video').evaluate(v => v.currentTime);
    expectNear(seekTime, 0.8, 0.12);
    passed.push('B7: slider seek changes real video currentTime (frame accuracy not tested)');

    await page.locator('input[type="file"]').setInputFiles(demo2);
    await page.waitForFunction(() => document.querySelector('video').readyState >= 2);
    const revoked = await page.evaluate(() => window.__revoked || []);
    assert.equal(revoked.length, 1, 'previous video blob URL should be revoked');
    passed.push('B8: second video replaces source and revokes prior object URL');

    assert.equal(unexpectedRequests.length, 0, 'unexpected network calls: ' + unexpectedRequests.join(', '));
    assert.equal(browserErrors.length, 0, 'uncaught browser JS errors: ' + browserErrors.join('; '));
    passed.push('B9: no uncaught page exceptions or extra external requests in offline fallback scenario');

    await page.screenshot({ path: path.resolve(__dirname, 'fixtures', 'browser-fallback.png'), fullPage: true });
    for (const line of passed) console.log('PASS ' + line);
    console.log('Chromium real-browser checks passed: ' + passed.length);
  } finally {
    await browser.close();
  }
}
main().catch(error => {
  console.error('BROWSER_SMOKE_TEST_FAILED:', error.stack || String(error));
  process.exitCode = 1;
});
