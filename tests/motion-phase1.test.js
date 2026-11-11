#!/usr/bin/env node
/* Regression checks for Phase 1. Local fake browser; not real Safari/Chromebook. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('index.html', 'utf8');
const matches = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
const code = matches.map((match) => match[1]).filter(Boolean).at(-1);
assert.ok(code && code.includes('class Player'), 'Inline Player script missing');
new vm.Script(code);

async function boot({ model = false, modelReject = false } = {}) {
  const calls = [];
  const revoked = [];
  let id = 0;
  const ctx = {
    clearRect: () => calls.push('clearRect'),
    drawImage: () => calls.push('drawImage'),
    fillRect: () => calls.push('fillRect'),
    beginPath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    stroke: () => {},
    arc: () => {},
    fill: () => {}
  };
  const video = {
    paused: true,
    ended: false,
    readyState: 4,
    videoWidth: 640,
    videoHeight: 360,
    duration: 6,
    currentTime: 0,
    playbackRate: 1,
    style: {},
    load() { if (this.onloadedmetadata) this.onloadedmetadata(); },
    play() { this.paused = false; if (this.onplay) this.onplay(); return Promise.resolve(); },
    pause() { this.paused = true; if (this.onpause) this.onpause(); }
  };
  const status = { textContent: '' };
  const input = { files: [] };
  const button = () => ({ textContent: '' });
  const elements = {
    video,
    canvas: { style: {}, width: 640, height: 360, getContext: () => ctx },
    'input[type=file]': input,
    '.playpause': button(),
    '.frameBack': button(),
    '.frameForward': button(),
    '.seek': { max: 1, value: 0 },
    '.speed': { value: '1' },
    '.stickToggle': { checked: true },
    '.flipBtn': button(),
    '.timeDisplay': { textContent: '' },
    '.status': status
  };
  const root = { querySelector: (selector) => {
    if (!(selector in elements)) throw Error('unknown selector: ' + selector);
    return elements[selector];
  }};
  const pose = model || modelReject ? {
    SupportedModels: { MoveNet: 'MoveNet' },
    movenet: { modelType: { SINGLEPOSE_THUNDER: 'Thunder' } },
    util: { getAdjacentPairs: () => [] },
    createDetector: async () => {
      if (modelReject) throw Error('blocked weights');
      return { estimatePoses: async () => [] };
    }
  } : undefined;
  const context = {
    window: { poseDetection: pose },
    poseDetection: pose,
    document: { getElementById: () => root },
    URL: {
      createObjectURL: () => 'blob:test-' + (++id),
      revokeObjectURL: (value) => revoked.push(value)
    },
    requestAnimationFrame: () => 7,
    cancelAnimationFrame: () => {},
    console: { error: () => {} }
  };
  await vm.runInNewContext(code, context);
  return { calls, revoked, video, status, elements };
}

(async function run() {
  let count = 0;
  const check = async (name, fn) => {
    await fn();
    count += 1;
    console.log('PASS ' + name);
  };
  await check('JS syntax and Player construction with CDN missing', async () => {
    const x = await boot();
    assert.equal(typeof x.video.onplay, 'function');
    assert.match(x.status.textContent, /モデルを読み込めません/);
  });
  await check('CDN missing: default stick ON still shows video on playback', async () => {
    const x = await boot();
    x.video.paused = false;
    x.video.onplay();
    await Promise.resolve();
    assert.ok(x.calls.includes('drawImage'), 'canvas must draw video');
    assert.ok(!x.calls.includes('fillRect'), 'no black canvas when model unavailable');
  });
  await check('Model download failure preserves visible video', async () => {
    const x = await boot({ modelReject: true });
    x.video.paused = false;
    x.video.onplay();
    await Promise.resolve();
    assert.ok(x.calls.includes('drawImage'));
    assert.ok(!x.calls.includes('fillRect'));
  });
  await check('Model failure warning persists after video metadata', async () => {
    const x = await boot();
    x.video.onloadedmetadata();
    assert.match(x.status.textContent, /モデル/);
  });
  await check('Model available: skeleton canvas still works', async () => {
    const x = await boot({ model: true });
    x.video.paused = false;
    x.video.onplay();
    await Promise.resolve();
    assert.ok(x.calls.includes('fillRect'), 'normal stick mode draws background');
  });
  await check('Switching videos revokes previous object URL', async () => {
    const x = await boot();
    x.elements['input[type=file]'].files = [{name:'demo1.mp4'}];
    x.elements['input[type=file]'].onchange();
    x.elements['input[type=file]'].files = [{name:'demo2.mp4'}];
    x.elements['input[type=file]'].onchange();
    assert.equal(x.revoked.length, 1);
    assert.equal(x.revoked[0], 'blob:test-1');
  });
  await check('Before video load, stick-toggle does not draw invalid media', async () => {
    const x = await boot();
    x.video.readyState = 0;
    x.video.videoWidth = 0;
    x.video.videoHeight = 0;
    x.elements['.stickToggle'].onchange();
    await Promise.resolve();
    assert.ok(!x.calls.includes('drawImage'), 'not allowed to draw unready video');
  });
  console.log('Ran ' + count + ' Phase-1 offline checks');
})().catch((err) => {
  console.error('FAIL ' + err.stack);
  process.exitCode = 1;
});
