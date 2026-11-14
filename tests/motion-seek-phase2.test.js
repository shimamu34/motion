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

async function boot({ model = false, deferredPose = false } = {}) {
  const draws = [];
  let rafCalls = 0;
  const rafCallbacks = [];
  const poseResolvers = [];
  const ctx = {
    clearRect: () => draws.push('clear'),
    drawImage: () => draws.push('video'),
    fillRect: () => draws.push('black'),
    beginPath() {},
    moveTo() {},
    lineTo() {},
    stroke() {},
    arc: () => draws.push('pose'),
    fill() {}
  };
  const video = {
    paused: true, ended: false, readyState: 4,
    videoWidth: 640, videoHeight: 360,
    currentTime: 0, duration: 8, seeking: false,
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
    '.smoothVideoToggle': { checked: false },
    '.poseModelSelect': { value: 'THUNDER', disabled: true },
    '.posePerf': { textContent: '' },
    '.flipBtn': button(),
    '.timeDisplay': { textContent: '' },
    '.status': { textContent: '' }
  };
  const pose = model ? {
    SupportedModels: { MoveNet: 'MoveNet' },
    movenet: { modelType: { SINGLEPOSE_THUNDER: 'THUNDER' } },
    createDetector: async () => ({
      estimatePoses: async () => {
        if (!deferredPose) return [];
        return new Promise(resolve => poseResolvers.push(resolve));
      }
    }),
    util: { getAdjacentPairs: () => [] }
  } : undefined;
  const root = { querySelector: selector => {
    if (!(selector in elems)) throw new Error('Unknown selector ' + selector);
    return elems[selector];
  }};
  const context = {
    window: { poseDetection: pose },
    poseDetection: pose,
    document: {
      getElementById: () => root,
      createElement(tag) {
        assert.equal(tag, 'canvas');
        return { width: 0, height: 0, getContext: () => ({ drawImage() {} }) };
      }
    },
    URL: { createObjectURL: () => 'blob:synthetic', revokeObjectURL() {} },
    requestAnimationFrame: callback => {
      rafCallbacks.push(callback);
      return ++rafCalls;
    },
    cancelAnimationFrame() {},
    console: { error() {} }
  };
  await vm.runInNewContext(code, context);
  return {
    video, elems, draws, ctx,
    get rafCalls() { return rafCalls; },
    get pendingPoseCount() { return poseResolvers.length; },
    runRaf: index => rafCallbacks[index](),
    resolvePose: (poses = []) => {
      const resolve = poseResolvers.shift();
      assert.ok(resolve, 'a pose inference must be pending');
      resolve(poses);
    }
  };
}

function painted(draws) {
  return draws.filter(value => value === 'video' || value === 'black');
}

async function flush() {
  // The synchronized drawing pipeline awaits a capture, serial model
  // inference and validation before it paints the display canvas.
  for (let i = 0; i < 16; i++) await Promise.resolve();
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

  await check('play during a pending seek does not start an early or duplicate loop', async () => {
    const x = await boot();
    x.elems['.seek'].value = 2;
    x.elems['.seek'].oninput();
    x.video.play();
    await flush();
    assert.deepEqual(painted(x.draws), [], 'play must not paint before seeked');
    assert.equal(x.rafCalls, 0, 'play must not start a render loop before seeked');
    x.video.onseeked();
    await flush();
    assert.equal(x.rafCalls, 1, 'seek completion must start exactly one loop');
    const paintsAfterSeek = painted(x.draws).length;
    x.video.onplay();
    await flush();
    assert.equal(x.rafCalls, 1, 'repeated play must not create another loop');
    assert.equal(painted(x.draws).length, paintsAfterSeek, 'repeated play must not repaint immediately');
  });

  await check('stale seeked events do not complete the latest seek', async () => {
    const x = await boot();
    x.elems['.seek'].value = 2;
    x.elems['.seek'].oninput();
    x.elems['.seek'].value = 5;
    x.elems['.seek'].oninput();
    x.video.currentTime = 2;
    x.video.onseeked();
    await flush();
    assert.deepEqual(painted(x.draws), [], 'old seeked event must be ignored');
    x.video.currentTime = 5;
    x.video.onseeked();
    await flush();
    assert.ok(painted(x.draws).includes('video'), 'latest seeked event must repaint');
  });

  await check('bounded seeked time quantization completes only after seeking ends', async () => {
    const x = await boot();
    x.elems['.seek'].value = 1 / 30;
    x.elems['.seek'].oninput();
    x.video.currentTime = 0.033;
    x.video.seeking = true;
    x.video.onseeked();
    await flush();
    assert.deepEqual(painted(x.draws), [], 'an event while media is still seeking must not complete');
    x.video.seeking = false;
    x.video.onseeked();
    await flush();
    assert.ok(painted(x.draws).includes('video'),
      'a bounded media-time quantization difference may complete after seeking ends');
  });

  await check('stale asynchronous pose results are discarded after a new seek', async () => {
    const x = await boot({ model: true, deferredPose: true });
    const pose = [{ keypoints: [{ x: 1, y: 1, score: 1 }] }];
    x.elems['.seek'].value = 2;
    x.elems['.seek'].oninput();
    x.video.onseeked();
    await flush();
    x.elems['.seek'].value = 4;
    x.elems['.seek'].oninput();
    x.resolvePose(pose);
    await flush();
    assert.equal(x.draws.filter(value => value === 'pose').length, 0,
      'pose result from the previous seek must not be drawn');
    x.video.onseeked();
    await flush();
    x.resolvePose(pose);
    await flush();
    await flush();
    assert.equal(x.draws.filter(value => value === 'pose').length, 1,
      'pose result for the current seek may be drawn');
  });

  await check('stale asynchronous pose results are discarded after video switching', async () => {
    const x = await boot({ model: true, deferredPose: true });
    const pose = [{ keypoints: [{ x: 1, y: 1, score: 1 }] }];
    x.elems['.seek'].value = 2;
    x.elems['.seek'].oninput();
    x.video.onseeked();
    await flush();
    x.elems['input[type=file]'].files = [{ name: 'replacement.mp4' }];
    x.elems['input[type=file]'].onchange();
    x.resolvePose(pose);
    await flush();
    await flush();
    assert.equal(x.draws.filter(value => value === 'pose').length, 0,
      'pose result from the previous video must not be drawn');
  });

  await check('video switching starts the new render while old inference is pending', async () => {
    const x = await boot({ model: true, deferredPose: true });
    x.video.play();
    await flush();
    assert.equal(x.pendingPoseCount, 1, 'the first video inference must be pending');
    x.elems['input[type=file]'].files = [{ name: 'replacement.mp4' }];
    x.elems['input[type=file]'].onchange();
    await flush();
    assert.equal(x.pendingPoseCount, 2,
      'the new video must start inference even while the old one is pending');
    x.resolvePose([]);
    await flush();
    assert.equal(x.draws.filter(value => value === 'pose').length, 0,
      'the old video inference must remain undisplayed');
    x.resolvePose([]);
  });

  await check('stopped unready render retries cannot revive an old loop', async () => {
    const x = await boot();
    x.video.readyState = 0;
    x.video.videoWidth = 0;
    x.video.videoHeight = 0;
    x.video.paused = false;
    x.video.onplay();
    assert.equal(x.rafCalls, 1, 'unready playback must queue one retry');
    x.elems['input[type=file]'].files = [{ name: 'replacement.mp4' }];
    x.elems['input[type=file]'].onchange();
    x.video.readyState = 4;
    x.video.videoWidth = 640;
    x.video.videoHeight = 360;
    x.runRaf(0);
    await flush();
    assert.equal(painted(x.draws).length, 0,
      'the old unready callback must not paint the new video');
    x.runRaf(1);
    await flush();
    assert.ok(painted(x.draws).length > 0, 'the new video callback must paint');
  });

  await check('same-time boundary seeks and video switching clear pending state', async () => {
    const x = await boot();
    x.elems['.seek'].value = 0;
    x.elems['.seek'].oninput();
    await flush();
    x.video.play();
    await flush();
    assert.ok(x.rafCalls > 0, 'a no-op seek must not block playback');

    const boundary = await boot();
    boundary.video.currentTime = 8;
    boundary.elems['.seek'].value = 8;
    boundary.elems['.seek'].oninput();
    boundary.video.play();
    await flush();
    assert.ok(boundary.rafCalls > 0, 'an end-time no-op seek must not block playback');

    const y = await boot();
    y.elems['.seek'].value = 2;
    y.elems['.seek'].oninput();
    y.elems['input[type=file]'].files = [{ name: 'replacement.mp4' }];
    y.elems['input[type=file]'].onchange();
    await flush();
    assert.ok(y.rafCalls > 0, 'video switching must clear pending seek state');
  });

  console.log('Ran ' + passed + ' Phase-2 offline seek timing checks');
})().catch(err => {
  console.error('FAIL ' + err.stack);
  process.exitCode = 1;
});
