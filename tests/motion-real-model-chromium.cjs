#!/usr/bin/env node
/**
 * Real MoveNet Thunder startup + estimatePoses smoke test in Chrome.
 * Uses synthetic geometric video; this does not establish human-pose accuracy.
 */
const {chromium} = require('playwright-core');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const here = __dirname;
const html = fs.readFileSync(path.resolve(here, '..','index.html'), 'utf8');
const fixtureDir=path.resolve(here,'fixtures');
const movie=path.join(fixtureDir,'synthetic-person.webm');
const monkeypatch = [
  '<script>',
  'window.__probe={created:false,estimates:0,poses:0,keypoints:0,maxScore:0,arcs:0,errors:[]};',
  '(function(){',
  'if (!window.poseDetection || !window.poseDetection.createDetector) return;',
  'const orig=window.poseDetection.createDetector.bind(window.poseDetection);',
  'window.poseDetection.createDetector=async function(...args){',
  ' const detector=await orig(...args);window.__probe.created=true;',
  ' const infer=detector.estimatePoses.bind(detector);',
  ' detector.estimatePoses=async function(...args){',
  '  try{const poses=await infer(...args);',
  '   window.__probe.estimates++;window.__probe.poses=poses.length;',
  '   window.__probe.keypoints=poses[0]?.keypoints?.length||0;',
  '   window.__probe.maxScore=Math.max(0,...poses.flatMap(p=>(p.keypoints||[]).map(k=>k.score||0)));',
  '   return poses;',
  '  }catch(e){window.__probe.errors.push(String(e));throw e;}',
  ' }; return detector;',
  '};',
  'const arc=CanvasRenderingContext2D.prototype.arc;',
  'CanvasRenderingContext2D.prototype.arc=function(...a){window.__probe.arcs++;return arc.apply(this,a);};',
  '})();',
  '</script>'
].join('\n');
const needle = '<script>\n(async () => {';
assert.ok(html.includes(needle),'Inline app script not found');
fs.mkdirSync(fixtureDir,{recursive:true});
const tempFile=path.join(fixtureDir,'real-model-instrumented.html');
fs.writeFileSync(tempFile,html.replace(needle,monkeypatch+'\n'+needle));
const timeout=135000;
async function main(){
 assert.ok(fs.existsSync(movie),'Synthetic video is missing');
 const browser=await chromium.launch({
   headless:true,executablePath:process.env.BROWSER_BIN||'/usr/bin/google-chrome',
   args:['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required',
     '--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']
 });
 try {
  const page=await browser.newPage({viewport:{width:1100,height:850}});
  const pageErrors=[], failedRequests=[], consoleErrors=[];
  page.on('pageerror',e=>pageErrors.push(String(e)));
  page.on('requestfailed',r=>failedRequests.push({url:r.url(),reason:r.failure()?.errorText}));
  page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text().slice(0,300));});
  await page.goto('file://'+tempFile,{waitUntil:'commit',timeout});
  const handle=await page.waitForFunction(()=>{
    const t=document.querySelector('.status')?.textContent||'';
    if(t.includes('姿勢モデルを読み込みました')) return 'READY';
    if(t.includes('姿勢モデルを読み込めません')) return 'FAILED';
    return false;
  },null,{timeout});
  const status=await handle.jsonValue();
  console.log('MODEL_INITIALIZATION: '+status);
  if(status!=='READY'){
    console.error('MODEL_FAILED_REQUESTS '+JSON.stringify(failedRequests.slice(0,12)));
    console.error('PAGE_ERRORS '+JSON.stringify(pageErrors.slice(0,12)));
    console.error('CONSOLE_ERRORS '+JSON.stringify(consoleErrors.slice(0,12)));
    throw Error('Real MoveNet model not successfully initialized in CI');
  }
  await page.locator('input[type=file]').setInputFiles(movie);
  await page.waitForFunction(()=>document.querySelector('video').readyState>=2
     && document.querySelector('video').videoWidth>0,null,{timeout:15000});
  await page.waitForFunction(()=>window.__probe?.estimates>0,null,{timeout:45000});
  const probe=await page.evaluate(()=>window.__probe);
  console.log('REAL_MOVENET_PROBE '+JSON.stringify(probe));
  assert.equal(probe.created,true);
  assert.ok(probe.estimates>0);
  assert.equal(probe.errors.length,0);
  assert.ok(Number.isFinite(probe.maxScore));
  await page.screenshot({path:path.join(fixtureDir,'real-model-screen.png'),fullPage:true});
  console.log('PASS M1: Real TensorFlow.js and MoveNet Thunder initialized');
  console.log('PASS M2: Actual app called real estimatePoses on synthetic WebM');
  console.log('PASS M3: Inference result was captured without errors');
  if(probe.arcs>0) console.log('PASS M4: Browser drew detected pose landmark arcs');
  else console.log('UNVERIFIED M4: No detectable landmarks on non-human geometric fixture');
  console.log('UNVERIFIED: real-human pose accuracy; iOS Safari; Chromebook');
 } finally { await browser.close(); }
}
main().catch(e=>{console.error('REAL_MODEL_TEST_FAILED: '+(e.stack||e));process.exitCode=1;});
