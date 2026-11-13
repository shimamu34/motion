'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, 'browser-device-smoke.html'), 'utf8');
const match = html.match(/<script>\s*([\s\S]*?)<\/script>/);
assert.ok(match, 'inline diagnostic JavaScript must exist');

function setup(poses, onEstimate = null) {
  const drawn = { strokes: 0, points: 0, clears: 0, snapshotCaptures: 0, synchronizedDraws: 0 };
  let inputSeen = null;
  let estimateCalls = 0;
  let configSeen = null;
  let nextFrameId = 1;
  const scheduledFrames = new Map();
  const ctx = {
    setTransform() {}, beginPath() {}, moveTo() {}, lineTo() {},
    stroke() { drawn.strokes++; },
    arc() { drawn.points++; },
    fill() {}, clearRect() { drawn.clears++; },
  };
  const ids = [
    'videoFile', 'video', 'mediaState', 'play', 'seek', 'frame',
    'speed', 'flip', 'model', 'infer', 'modelState',
    'copy', 'reset', 'report', 'poseOverlay', 'poseState', 'follow',
    'syncFrame', 'timeline', 'timelineTime'
  ];
  const elements = {};
  for (const id of ids) {
    elements[id] = {
      style: {},
      disabled: false,
      textContent: '',
      listeners: {},
      addEventListener(event, fn) { this.listeners[event] = fn; },
      removeEventListener() {},
    };
  }
  const video = elements.video;
  Object.assign(video, {
    duration: 10, readyState: 4, videoWidth: 640, videoHeight: 360,
    clientWidth: 640, clientHeight: 360, currentTime: 3, paused: true,
    pause() { this.paused = true; },
    play() { this.paused = false; return Promise.resolve(); },
    removeAttribute() {}, load() {},
  });
  const overlay = elements.poseOverlay;
  overlay.width = 0;
  overlay.height = 0;
  overlay.getContext = () => ctx;
  const synchronized = elements.syncFrame;
  synchronized.hidden = true;
  synchronized.getContext = () => ({ setTransform() {}, fillRect() {},
    drawImage() { drawn.synchronizedDraws++; } });
  const snapshot = { width:0, height:0, getContext: () => ({
    drawImage() { drawn.snapshotCaptures++; } }) };
  const poseDetection = {
    SupportedModels: { MoveNet: 'MoveNet' },
    movenet: { modelType: { SINGLEPOSE_THUNDER: 'SINGLEPOSE_THUNDER' } },
    createDetector: async (_, config) => {
      configSeen = config;
      return { estimatePoses: async input => {
        estimateCalls++;
        inputSeen = input;
        if (onEstimate) await onEstimate(input, video);
        return poses;
      } };
    },
  };
  const fakeWindow = {
    tf: {}, poseDetection, devicePixelRatio: 1,
    addEventListener() {},
  };
  vm.runInNewContext(match[1], {
    window: fakeWindow, document: {
      getElementById: id => elements[id],
      createElement: tag => { assert.equal(tag, "canvas"); return snapshot; },
    },
    poseDetection, navigator: { clipboard: { writeText: async () => {} } },
    URL: { createObjectURL() { return 'blob:local-synthetic-video'; }, revokeObjectURL() {} },
    setTimeout, clearTimeout, console,
    requestAnimationFrame: callback => {
      const id = nextFrameId++;
      scheduledFrames.set(id, callback);
      return id;
    },
    cancelAnimationFrame: id => scheduledFrames.delete(id),
  }, { filename: 'browser-device-smoke.html', timeout: 5000 });
  return {
    elements, drawn,
    get inputSeen() { return inputSeen; },
    get snapshot() { return snapshot; },
    get estimateCalls() { return estimateCalls; },
    get configSeen() { return configSeen; },
    get pendingFrames() { return scheduledFrames.size; },
    async tick() {
      const next = scheduledFrames.entries().next().value;
      if (!next) return;
      const [id, frame] = next;
      scheduledFrames.delete(id);
      await frame();
    },
    async infer() {
      await elements.model.listeners.click();
      await elements.infer.listeners.click();
      return JSON.parse(elements.report.textContent);
    },
  };
}

test('NoPosesInFrame never reports overlay PASS or draws skeleton', async () => {
  const app = setup([]);
  const result = await app.infer();
  assert.equal(result.movenet_thunder_load, 'PASS');
  assert.equal(result.movenet_thunder_inference, 'FAIL'); // file must be selected first
  assert.equal(result.pose_visualization, 'NOT_TESTED');
});

test('real pose results draw 12 skeleton edges and 17 joint dots in canvas', async () => {
  const points = Array.from({ length: 17 }, (_, i) => ({
    x: 15 + i * 18, y: 12 + i * 11, score: 0.95,
  }));
  const app = setup([{ keypoints: points }]);
  // Simulate a locally loaded video (never upload a frame).
  app.elements.videoFile.files = [{ type: 'video/mp4' }];
  app.elements.videoFile.listeners.change();
  app.elements.video.readyState = 4;
  app.elements.video.duration = 10;
  // The file change handler needs a loadeddata signal to mark the decode.
  app.elements.video.listeners.loadeddata();
  const result = await app.infer();
  assert.equal(result.movenet_thunder_inference, 'PASS');
  assert.equal(result.pose_visualization, 'PASS');
  assert.equal(app.drawn.strokes, 12);
  assert.equal(app.drawn.points, 17);
});

test('no pose after model call reports NoPosesInFrame and zero skeleton lines', async () => {
  const app = setup([]);
  app.elements.videoFile.files = [{ type: 'video/mp4' }];
  app.elements.videoFile.listeners.change();
  app.elements.video.readyState = 4;
  app.elements.video.duration = 10;
  app.elements.video.listeners.loadeddata();
  const result = await app.infer();
  assert.equal(result.movenet_thunder_inference, 'PASS');
  assert.equal(result.movenet_thunder_inference_detail, 'NoPosesInFrame');
  assert.equal(result.pose_visualization, 'NO_POSE');
  assert.equal(app.drawn.strokes, 0);
});

test('mirroring applies to BOTH video and pose overlay', () => {
  const app = setup([]);
  app.elements.flip.listeners.click();
  assert.equal(app.elements.video.style.transform, 'scaleX(-1)');
  assert.equal(app.elements.poseOverlay.style.transform, 'scaleX(-1)');
  assert.equal(app.elements.syncFrame.style.transform, 'scaleX(-1)');
});

test('seeking clears previously drawn skeleton', () => {
  const app = setup([]);
  const before = app.drawn.clears;
  app.elements.video.listeners.seeked();
  assert.ok(app.drawn.clears > before);
});


test('diagnostic requests a lower person threshold for previously missed poses', async () => {
  const app = setup([]);
  await app.elements.model.listeners.click();
  assert.equal(app.configSeen.minPoseScore, 0.10);
  assert.equal(app.elements.follow.disabled, false);
});

test('continuous tracking draws skeleton while video is playing without concurrent loops', async () => {
  const points = Array.from({ length: 17 }, (_, i) => ({x: 20+i*11, y: 30+i*8, score: 0.92}));
  const app = setup([{keypoints: points}]);
  app.elements.videoFile.files = [{type: 'video/mp4'}];
  app.elements.videoFile.listeners.change();
  app.elements.video.readyState = 4;
  app.elements.video.duration = 10;
  app.elements.video.listeners.loadeddata();
  await app.elements.model.listeners.click();
  app.elements.follow.listeners.click();
  assert.equal(app.pendingFrames, 0); // paused: no background inference
  await app.elements.video.play();
  app.elements.video.listeners.play();
  assert.equal(app.pendingFrames, 1);
  await app.tick();
  const report = JSON.parse(app.elements.report.textContent);
  assert.equal(report.pose_follow, 'ON');
  assert.equal(report.pose_follow_updates, 1);
  assert.equal(report.pose_follow_poses_found, 1);
  assert.equal(report.pose_visualization, 'PASS');
  assert.ok(app.drawn.strokes >= 12);
  assert.equal(app.pendingFrames, 1);
  assert.equal(app.inputSeen, app.snapshot, "MoveNet must infer on the captured frame");
  assert.equal(app.drawn.snapshotCaptures, 1);
  assert.equal(app.drawn.synchronizedDraws, 1);
  assert.equal(app.elements.syncFrame.hidden, false);
  assert.equal(report.pose_follow_mode, "SYNCHRONIZED_SNAPSHOT");
  assert.equal(typeof report.pose_follow_last_inference_ms, "number");
  assert.equal(typeof report.pose_follow_video_lag_ms, "number");
  app.elements.follow.listeners.click();
  assert.equal(app.pendingFrames, 0);
  assert.equal(JSON.parse(app.elements.report.textContent).pose_follow, 'OFF');
  assert.equal(app.elements.syncFrame.hidden, true);
});

test('continuous tracking reports zero-person inference instead of displaying ghost skeleton', async () => {
  const app = setup([]);
  app.elements.videoFile.files = [{type: 'video/mp4'}];
  app.elements.videoFile.listeners.change();
  app.elements.video.readyState = 4;
  app.elements.video.duration = 10;
  app.elements.video.listeners.loadeddata();
  await app.elements.model.listeners.click();
  app.elements.follow.listeners.click();
  await app.elements.video.play();
  app.elements.video.listeners.play();
  await app.tick();
  const report = JSON.parse(app.elements.report.textContent);
  assert.equal(report.movenet_thunder_inference_detail, 'NoPosesInFrame');
  assert.equal(report.pose_visualization, 'NO_POSE');
  assert.equal(report.pose_follow_poses_found, 0);
  assert.equal(app.drawn.strokes, 0);
});

test('replacing a video stops tracking and cancels its next animation callback', async () => {
  const app = setup([]);
  app.elements.videoFile.files = [{type: 'video/mp4'}];
  app.elements.videoFile.listeners.change();
  app.elements.video.readyState = 4;
  app.elements.video.duration = 10;
  app.elements.video.listeners.loadeddata();
  await app.elements.model.listeners.click();
  app.elements.follow.listeners.click();
  await app.elements.video.play();
  app.elements.video.listeners.play();
  assert.equal(app.pendingFrames, 1);
  app.elements.videoFile.files = [{type: 'video/mp4'}];
  app.elements.videoFile.listeners.change();
  assert.equal(app.pendingFrames, 0);
  assert.equal(JSON.parse(app.elements.report.textContent).pose_follow, 'OFF');
});

test('slow inference drops a stale snapshot rather than misaligning the skeleton', async () => {
  const points = Array.from({length:17}, (_,i)=>({x:i*10,y:i*9,score:.98}));
  const app = setup([{keypoints:points}], async (_input, video) => {
    video.currentTime += 2;
  });
  app.elements.videoFile.files = [{type:'video/mp4'}];
  app.elements.videoFile.listeners.change();
  app.elements.video.readyState = 4;
  app.elements.video.duration = 10;
  app.elements.video.listeners.loadeddata();
  await app.elements.model.listeners.click();
  app.elements.follow.listeners.click();
  await app.elements.video.play();
  app.elements.video.listeners.play();
  await app.tick();
  const result = JSON.parse(app.elements.report.textContent);
  assert.equal(result.pose_visualization, 'STALE_FRAME');
  assert.equal(result.pose_follow_stale_drops, 1);
  assert.equal(result.pose_follow_updates, 0);
  assert.equal(app.elements.syncFrame.hidden, true);
  assert.equal(app.drawn.strokes, 0);
});

test('timeline seek hides a synchronized snapshot until the next inferred frame', async () => {
  const points = Array.from({length:17}, (_,i)=>({x:i+12,y:i+8,score:.9}));
  const app = setup([{keypoints:points}]);
  app.elements.videoFile.files = [{type:'video/mp4'}];
  app.elements.videoFile.listeners.change();
  app.elements.video.listeners.loadeddata();
  await app.elements.model.listeners.click();
  app.elements.follow.listeners.click();
  await app.elements.video.play();
  app.elements.video.listeners.play();
  await app.tick();
  assert.equal(app.elements.syncFrame.hidden, false);
  app.elements.timeline.value = '6.5';
  app.elements.timeline.listeners.change();
  assert.equal(app.elements.video.currentTime, 6.5);
  assert.equal(app.elements.syncFrame.hidden, true);
});

test('stopping during inference prevents out-of-date snapshot repaint', async () => {
  let release;
  const blocked = new Promise(resolve => { release = resolve; });
  const points = Array.from({length:17}, (_,i)=>({x:i+3,y:i+3,score:.9}));
  const app = setup([{keypoints:points}], async () => { await blocked; });
  app.elements.videoFile.files = [{type:'video/mp4'}];
  app.elements.videoFile.listeners.change();
  app.elements.video.listeners.loadeddata();
  await app.elements.model.listeners.click();
  app.elements.follow.listeners.click();
  await app.elements.video.play();
  app.elements.video.listeners.play();
  const pending = app.tick();
  app.elements.follow.listeners.click();
  release();
  await pending;
  assert.equal(app.elements.syncFrame.hidden, true);
  assert.equal(app.drawn.synchronizedDraws, 0);
  assert.equal(app.pendingFrames, 0);
});
