#!/usr/bin/env node
/*
 * Linux Playwright WebKit engine test; NOT iOS Safari or a Chromebook.
 * Two locally generated MP4 videos only; test CDN failure fallback.
 */
const {webkit}=require('playwright-core');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const movie1=path.resolve(__dirname,'fixtures','webkit-a.mp4');
const movie2=path.resolve(__dirname,'fixtures','webkit-b.mp4');
async function main(){
 assert.ok(fs.existsSync(movie1)&&fs.existsSync(movie2),'Synthetic MP4 fixtures missing');
 const browser=await webkit.launch({headless:true});
 let passes=0;
 const check=(msg)=>{console.log('PASS WK'+(++passes)+': '+msg);};
 try{
  const page=await browser.newPage({viewport:{width:1000,height:800}});
  const exceptions=[];
  page.on('pageerror',err=>exceptions.push(String(err)));
  await page.route('https://cdn.jsdelivr.net/**',route=>route.abort('failed'));
  await page.goto('file://'+path.join(root,'index.html'),{waitUntil:'load',timeout:60000});
  await page.waitForFunction(()=>document.querySelector('.status')?.textContent.includes('姿勢モデルを読み込めません'),null,{timeout:30000});
  check('WebKit started player despite blocked model scripts');

  await page.locator('input[type=file]').setInputFiles(movie1);
  await page.waitForFunction(()=>{
    const v=document.querySelector('video');return v.readyState>=2 && v.videoWidth>0;
  },null,{timeout:12000});
  const dims=await page.locator('video').evaluate(v=>[v.videoWidth,v.videoHeight]);
  assert.ok(dims[0]>0 && dims[1]>0);
  check('WebKit decoded local synthetic H.264 video');

  const playing=await page.locator('video').evaluate(async v=>{
    if(v.paused){try{await v.play();}catch(e){return false;}}
    return !v.paused;
  });
  assert.equal(playing,true,'WebKit video did not play');
  await page.waitForFunction(()=>document.querySelector('video').currentTime>0.2,null,{timeout:10000});
  check('WebKit advanced actual playback time without model');

  await page.locator('.playpause').click();
  assert.equal(await page.locator('video').evaluate(v=>v.paused),true);
  await page.locator('.speed').selectOption('1.5');
  assert.equal(await page.locator('video').evaluate(v=>v.playbackRate),1.5);
  check('Play/pause and speed change work in WebKit');

  await page.locator('.flipBtn').click();
  assert.equal(await page.locator('video').evaluate(v=>v.style.transform),'scaleX(-1)');
  await page.locator('.seek').evaluate(el=>{
   el.value='0.7';el.dispatchEvent(new Event('input',{bubbles:true}));
  });
  await page.waitForFunction(()=>document.querySelector('video').currentTime>=0.6,null,{timeout:10000});
  check('Mirror and slider seek work in WebKit');

  await page.locator('input[type=file]').setInputFiles(movie2);
  await page.waitForFunction(()=>document.querySelector('video').readyState>=2,null,{timeout:12000});
  check('WebKit switched to second test video');

  assert.equal(exceptions.length,0,'Uncaught JS errors: '+exceptions.join(', '));
  check('No uncaught page exceptions');
  await page.screenshot({path:path.resolve(__dirname,'fixtures','webkit-fallback.png'),fullPage:true});
  console.log('WEBKIT_LINUX_PASS: '+passes+' checks (not iOS Safari)');
 }finally{await browser.close();}
}
main().catch(e=>{console.error('WEBKIT_LINUX_FAILED: '+(e.stack||e));process.exitCode=1;});
