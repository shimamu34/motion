'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, 'browser-device-smoke.html'), 'utf8');
const match = html.match(/<script>\s*([\s\S]*?)<\/script>/);
assert.ok(match, 'inline diagnostic JavaScript must exist');

function setup(poses) {
  const drawn = { strokes: 0, points: 0, clears: 0 };
  const ctx = {
    setTransform() {}, beginPath() {}, moveTo() {}, lineTo() {},
    stroke() { drawn.strokes++; },
    arc() { drawn.points++; },
    fill() {}, clearRect() { drawn.clears++; },
  };
  const ids = [
    'videoFile', 'video', 'mediaState', 'play', 'seek', 'frame',
    'speed', 'flip', 'model', 'infer', 'modelState',
    'copy', 'reset', 'report', 'poseOverlay', 'poseState'
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
  const poseDetection = {
    SupportedModels: { MoveNet: 'MoveNet' },
    movenet: { modelType: { SINGLEPOSE_THUNDER: 'SINGLEPOSE_THUNDER' } },
    createDetector: async () => ({ estimatePoses: async () => poses }),
  };
  const fakeWindow = {
    tf: {}, poseDetection, devicePixelRatio: 1,
    addEventListener() {},
  };
  vm.runInNewContext(match[1], {
    window: fakeWindow, document: { getElementById: id => elements[id] },
    poseDetection, navigator: { clipboard: { writeText: async () => {} } },
    URL: { createObjectURL() { return 'blob:local-synthetic-video'; }, revokeObjectURL() {} },
    setTimeout, clearTimeout, console,
  }, { filename: 'browser-device-smoke.html', timeout: 5000 });
  return {
    elements, drawn,
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
});

test('seeking clears previously drawn skeleton', () => {
  const app = setup([]);
  const before = app.drawn.clears;
  app.elements.video.listeners.seeked();
  assert.ok(app.drawn.clears > before);
});
