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

async function boot({ model = false, modelReject = false, modelDelay = false, poseOnEstimate = null } = {}) {
  const calls = [];
  const poseInputs = [];
  const displayedFrames = [];
  const capturedFrames = [];
  const revoked = [];
  const rafs = [];
  let resolveModel;
  let id = 0;
  const ctx = {
    clearRect: () => calls.push('clearRect'),
    drawImage: (source) => {
      calls.push('drawImage');
      displayedFrames.push(source);
    },
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
    '.smoothVideoToggle': { checked: false },
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
      if (modelDelay) await new Promise(resolve => { resolveModel = resolve; });
      if (modelReject) throw Error('blocked weights');
      return { estimatePoses: async source => {
        poseInputs.push(source);
        return poseOnEstimate ? await poseOnEstimate(source) : [];
      } };
    }
  } : undefined;
  const context = {
    window: { poseDetection: pose },
    poseDetection: pose,
    document: {
      getElementById: () => root,
      createElement(tag) {
        assert.equal(tag, 'canvas');
        const frame = {width: 0, height: 0, getContext: () => ({
          drawImage: source => {
            assert.equal(source, video, 'snapshot must capture the current video frame');
            capturedFrames.push(frame);
          }
        })};
        return frame;
      }
    },
    URL: {
      createObjectURL: () => 'blob:test-' + (++id),
      revokeObjectURL: (value) => revoked.push(value)
    },
    requestAnimationFrame: callback => { rafs.push(callback); return rafs.length; },
    cancelAnimationFrame: () => {}, 
    console: { error: () => {} }
  };
  const bootPromise = vm.runInNewContext(code, context);
  if (!modelDelay) await bootPromise;
  return { calls, revoked, video, status, elements, rafs, poseInputs, displayedFrames, capturedFrames,
    finishModel: async () => { if (resolveModel) resolveModel(); await bootPromise; } };
}

const flushMicrotasks = async () => {
  for (let i = 0; i < 12; i++) await Promise.resolve();
};

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
  await check('Delayed model download failure preserves guidance and video controls', async () => {
    const x = await boot({ modelReject: true, modelDelay: true });
    const flush = async () => {
      for (let i = 0; i < 6; i++) await Promise.resolve();
    };
    x.elements['input[type=file]'].files = [{ name: 'demo.mp4' }];
    x.elements['input[type=file]'].onchange();
    await flush();
    assert.equal(x.video.paused, false, 'video starts while the model is loading');

    await x.finishModel();
    assert.match(x.status.textContent, /姿勢モデルを読み込めません/);
    assert.match(x.status.textContent, /再生・停止・速度変更・シークは利用できます/);
    assert.equal(x.video.paused, false, 'model failure must not interrupt playback');
    x.calls.length = 0;
    assert.ok(x.rafs.length > 0, 'playback has a queued render frame');
    await x.rafs.shift()();
    assert.ok(x.calls.includes('drawImage'), 'playback still paints video after failure');
    assert.ok(!x.calls.includes('fillRect'), 'failed model must not hide video');

    x.video.onloadedmetadata();
    assert.match(x.status.textContent, /姿勢モデルは使えませんが、動画は操作できます/);
    const warning = x.status.textContent;
    x.elements['.playpause'].onclick();
    await flush();
    assert.equal(x.video.paused, true, 'pause control remains usable');
    x.elements['.speed'].value = '0.5';
    x.elements['.speed'].onchange();
    assert.equal(x.video.playbackRate, 0.5, 'speed control remains usable');

    x.calls.length = 0;
    x.elements['.seek'].value = 2.5;
    x.elements['.seek'].oninput();
    assert.equal(x.video.currentTime, 2.5, 'seek control still changes media time');
    x.video.onseeked();
    await flush();
    assert.ok(x.calls.includes('drawImage'), 'seek completion paints the video');
    assert.ok(!x.calls.includes('fillRect'), 'seek must preserve visible video');
    x.calls.length = 0;
    x.elements['.playpause'].onclick();
    await flush();
    assert.equal(x.video.paused, false, 'play control resumes after seeking');
    assert.ok(x.calls.includes('drawImage'), 'resumed playback paints video');
    assert.equal(x.status.textContent, warning, 'controls preserve the failure guidance');
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
    await flushMicrotasks();
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

  await check('Playback before video is ready schedules retry and eventually draws', async () => {
    const x = await boot({ model: true });
    x.video.paused = false;
    x.video.readyState = 0;
    x.video.videoWidth = 0;
    x.video.videoHeight = 0;
    x.video.onplay();
    assert.equal(x.rafs.length, 1, 'a retry frame should be queued during media loading');
    x.video.readyState = 4;
    x.video.videoWidth = 640;
    x.video.videoHeight = 360;
    x.rafs.shift()();
    await flushMicrotasks();
    assert.ok(x.calls.includes('fillRect'), 'render resumes as soon as video is ready');
  });

  await check('Model loaded during playback does not start a second render loop', async () => {
    const x = await boot({ model: true, modelDelay: true });
    x.video.paused = false;
    x.video.onplay();
    await Promise.resolve();
    assert.equal(x.rafs.length, 1, 'one render loop before model is available');
    await x.finishModel();
    await Promise.resolve();
    assert.equal(x.rafs.length, 1, 'model creation must not launch a second render loop');
  });

  await check('Synchronous video.play failure shows a user-facing error', async () => {
    const x = await boot();
    x.video.play = () => { throw Error('synchronous browser play failure'); };
    x.elements['.playpause'].onclick();
    assert.match(x.status.textContent, /動画を再生できませんでした/);
  });

  await check('Promise rejection from video.play shows a user-facing error', async () => {
    const x = await boot();
    x.video.play = () => Promise.reject(Error('play rejected'));
    x.elements['.playpause'].onclick();
    await Promise.resolve();
    assert.match(x.status.textContent, /動画を再生できませんでした/);
  });
  await check('Pose detector gets same sampled frame that real-video mode displays', async () => {
    const keypoints = Array.from({length: 17}, (_, i) => ({
      x: 10 + i * 13, y: 9 + i * 9, score: 0.95
    }));
    const x = await boot({ model: true, poseOnEstimate: async () => [{keypoints}] });
    x.elements['.stickToggle'].checked = false;
    x.video.paused = false;
    x.video.onplay();
    await flushMicrotasks();
    assert.equal(x.poseInputs.length, 1, 'one detector inference after one rendered frame');
    assert.equal(x.capturedFrames.length, 1);
    assert.ok(x.displayedFrames.includes(x.poseInputs[0]),
      'the video display must use the exact captured frame sent to MoveNet');
    assert.equal(x.poseInputs[0].width, 640);
    assert.equal(x.poseInputs[0].height, 360);
  });

  await check('Optional smooth mode keeps native video visible and still draws skeleton', async () => {
    const keypoints = Array.from({length:17}, (_,i) => ({
      x: 15+i*12, y: 10+i*10, score: 0.98
    }));
    const x = await boot({ model: true, poseOnEstimate: async () => [{keypoints}] });
    x.elements['.stickToggle'].checked = false;
    x.elements['.smoothVideoToggle'].checked = true;
    x.video.paused = false;
    x.video.onplay();
    await flushMicrotasks();
    assert.equal(x.poseInputs.length, 1);
    assert.equal(x.capturedFrames.length, 1, 'MoveNet should still infer from a captured frame');
    assert.equal(x.displayedFrames.length, 0,
      'transparent overlay must not cover the browser-native video with stale frames');
    assert.ok(x.calls.includes('clearRect'), 'existing overlay should be cleared');
    x.elements['.smoothVideoToggle'].checked = false;
    x.elements['.smoothVideoToggle'].onchange();
    await flushMicrotasks();
    assert.ok(x.calls.includes('clearRect'), 'sync mode change clears stale drawing immediately');
  });

  await check('Stick mode remains opaque black even with smooth-video option on', async () => {
    const x = await boot({ model: true });
    x.elements['.smoothVideoToggle'].checked = true;
    x.video.paused = false;
    x.video.onplay();
    await flushMicrotasks();
    assert.ok(x.calls.includes('fillRect'), 'stick picture still needs an opaque black background');
    assert.equal(x.displayedFrames.length, 0, 'stick picture hides native video');
  });

  await check('Paused frame is re-inferred and drawn against its own snapshot', async () => {
    const x = await boot({ model: true });
    x.video.paused = false;
    x.video.onplay();
    await flushMicrotasks();
    assert.equal(x.poseInputs.length, 1);
    x.video.pause();
    await flushMicrotasks();
    assert.equal(x.poseInputs.length, 2,
      'pause should re-infer from the stopped frame rather than reuse an old pose');
    assert.notEqual(x.poseInputs[1], x.poseInputs[0]);
    assert.ok(x.calls.includes('fillRect'));
  });

  await check('Production MoveNet limits model input to 640px for large video', async () => {
    const x = await boot({ model: true });
    x.video.videoWidth = 3840;
    x.video.videoHeight = 2160;
    x.video.onloadedmetadata();
    assert.equal(x.elements.canvas.width, 640);
    assert.equal(x.elements.canvas.height, 360);
    x.video.paused = false;
    x.video.onplay();
    await flushMicrotasks();
    assert.equal(x.poseInputs[0].width, 640);
    assert.equal(x.poseInputs[0].height, 360);
  });

  console.log('Ran ' + count + ' Phase-1 offline checks');
})().catch((err) => {
  console.error('FAIL ' + err.stack);
  process.exitCode = 1;
});
