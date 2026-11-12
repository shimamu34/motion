#!/usr/bin/env node
/* Phase-2 H2 regression: fake media events, NOT browser video verification.
 * These tests intentionally fail against main until Manus fixes seek timing.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('index.html', 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
const code = scripts.map(match => match[1]).filter(Boolean).at(-1);
assert.ok(code && code.includes('class Player'), 'Player script not found');
new vm.Script(code);

async function boot({ model = false } = {}) {
  const draws = [];
  const ctx = {
    clearRect: () => draws.push('clear'),
    drawImage: () => draws.push('video'),
    fillRect: () => draws.push('black'),
    beginPath() {},
    moveTo() {},
    lineTo() {},
    stroke() {},
    arc() {},
    fill() {}
  };
  const video = {
    paused: true, ended: false, readyState: 4,
    videoWidth: 640, videoHeight: 360,
    currentTime: 0, duration: 8,
    playbackRate: 1, style: {},
    load() {},
    pause() {
      this.paused = true;
      if (this.onpause) this.onpause();
    },
    play() {
      this.paused = false;
      if (this.onplay) this.onplay();
      return Promise.resolve();
    }
  };
  const button = () => ({ textContent: '' });
  const elems = {
    video,
    canvas: { style: {}, width: 640, height: 360, getContext: () => ctx },
    'input[type=file]': { files: [] },
    '.playpause': button(),
    '.frameBack': button(),
    '.frameForward': button(),
    '.seek': { value: 0, max: 8 },
    '.speed': { value: '1' },
    '.stickToggle': { checked: model },
    '.flipBtn': button(),
    '.timeDisplay': { textContent: '' },
    '.status': { textContent: '' }
  };
  const pose = model ? {
    SupportedModels: { MoveNet: 'MoveNet' },
    movenet: { modelType: { SINGLEPOSE_THUNDER: 'THUNDER' } },
    createDetector: async () => ({ estimatePoses: async () => [] }),
    util: { getAdjacentPairs: () => [] }
  } : undefined;
  const root = { querySelector: selector => {
    if (!(selector in elems)) throw new Error('Unknown selector ' + selector);
    return elems[selector];
  }};
  const context = {
    window: { poseDetection: pose },
    poseDetection: pose,
    document: { getElementById: () => root },
    URL: { createObjectURL: () => 'blob:synthetic', revokeObjectURL() {} },
    requestAnimationFrame: () => 1,
    cancelAnimationFrame() {},
    console: { error() {} }
  };
  await vm.runInNewContext(code, context);
  return { video, elems, draws, ctx };
}

function painted(draws) {
  return draws.filter(value => value === 'video' || value === 'black');
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

(async () => {
  let passed = 0;
  async function check(name, fn) {
    await fn();
    console.log('PASS ' + name);
    passed++;
  }

  await check('paused slider seek waits for seeked before painting', async () => {
    const x = await boot();
    x.elems['.seek'].value = 2.5;
    x.elems['.seek'].oninput();
    await flush();
    assert.deepEqual(painted(x.draws), [], 'must not paint old frame before seeked');
    assert.equal(x.video.currentTime, 2.5);
    x.video.onseeked();
    await flush();
    assert.ok(painted(x.draws).includes('video'), 'must display video after seeked');
  });

  await check('slider seek while playing avoids pre-seek pause repaint', async () => {
    const x = await boot();
    x.video.paused = false;
    x.elems['.seek'].value = 3.5;
    x.elems['.seek'].oninput();
    await flush();
    assert.deepEqual(painted(x.draws), [], 'pause handler must not paint old frame before seeked');
    assert.equal(x.video.paused, true);
    x.video.onseeked();
    await flush();
    assert.ok(painted(x.draws).includes('video'));
  });

  await check('frame-step while playing also waits for seek completion', async () => {
    const x = await boot();
    x.video.paused = false;
    x.elems['.frameForward'].onclick();
    await flush();
    assert.deepEqual(painted(x.draws), [], 'step must not repaint old frame before seeked');
    assert.ok(x.video.currentTime > 0);
    x.video.onseeked();
    await flush();
    assert.ok(painted(x.draws).includes('video'));
  });

  await check('rapid paused slider moves do not pre-paint intermediate frames', async () => {
    const x = await boot();
    x.elems['.seek'].value = 1;
    x.elems['.seek'].oninput();
    x.elems['.seek'].value = 5;
    x.elems['.seek'].oninput();
    await flush();
    assert.deepEqual(painted(x.draws), [], 'intermediate positions should not paint');
    assert.equal(x.video.currentTime, 5);
    x.video.onseeked();
    await flush();
    assert.ok(painted(x.draws).includes('video'));
  });

  await check('model-ready stick mode also waits for seek completion', async () => {
    const x = await boot({ model: true });
    x.elems['.seek'].value = 4;
    x.elems['.seek'].oninput();
    await flush();
    assert.deepEqual(painted(x.draws), [], 'skeleton mode must wait for seeked');
    x.video.onseeked();
    await flush();
    assert.ok(painted(x.draws).includes('black'), 'stick canvas should redraw after seeked');
  });

  console.log('Ran ' + passed + ' Phase-2 offline seek timing checks');
})().catch(err => {
  console.error('FAIL ' + err.stack);
  process.exitCode = 1;
});
