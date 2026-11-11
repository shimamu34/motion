# Approved Manus review task for motion PR #2
- PR: https://github.com/shimamu34/motion/pull/2
- Head SHA: e19ebdbab3839821467bb6f807f217573f85b436
- Manus task: https://manus.im/app/8Pfac5KwtxZfKCgi2CD7Cb
- Manus task ID: 8Pfac5KwtxZfKCgi2CD7Cb
- Scope: read-only review, one task; no merge
- Status: REVIEW_COMPLETED
- Credits reported: 18

## Review text (untrusted until independently checked)

## レビュー結果

対象HEAD `e19ebdbab3839821467bb6f807f217573f85b436` と親コミット `6134d8191afeef453e1cc817cfa64c3c2bd900c1`、PRベースからの全3ファイル差分、および `index.html` の関連元コードを読みました。書き込み、PR更新、マージ、デプロイは実施していません。

結論として、前回の **High 1件とMedium 2件は、今回のHEAD上ではコード上解消されています**。ただし、実Chrome/Safari、実動画、実CDN障害、実MoveNet Thunderを今回のレビュー環境では実施していないため、それらを実ブラウザ合格とは扱いません。

### 前回指摘の再確認

#### High: 描画準備前に `render()` が終了する問題 — 解消

- **ファイル:** `index.html`
- **行:** 281–301
- **判定:** 解消

今回、動画がまだ描画可能でない場合に単純に終了せず、再生中なら次のAnimationFrameで再試行する実装に変わっています。

```js
if (this.video.readyState < 2 || !this.video.videoWidth || !this.video.videoHeight) {
  if (!this.video.paused && !this.video.ended) {
    this.animationId = requestAnimationFrame(() => this.render());
  }
  return;
}
```

動画準備前に `onplay` が発火しても、準備完了後に描画ループが再開される構造です。追加テストでも、準備前に再試行が予約され、準備後に `fillRect()` が呼ばれることを確認しています。

#### Medium: モデル読込完了時の二重描画ループ — 解消

- **ファイル:** `index.html`
- **行:** 404–411
- **判定:** 解消

モデル読込完了時の以下の追加呼出しが削除されています。

```js
if (!player.video.paused) player.render();
```

現在は `onplay` が描画ループを所有し、モデル読込完了時には `detector` を有効化するだけです。したがって、再生中にモデルが読み込まれても、モデル完了処理が別のループを追加することはありません。

#### Medium: `play()` の同期例外 — 解消

- **ファイル:** `index.html`
- **行:** 228–238
- **判定:** 解消

`video.play()` 自体を `try/catch` で囲み、Promise拒否時と同じステータスを表示するようになっています。

```js
try {
  const playPromise = this.video.play();
  ...
} catch (error) {
  this.setStatus('動画を再生できませんでした。再生ボタンをもう一度押してください。');
}
```

同期例外とPromise拒否の両方を追加オフラインテストで確認し、成功しました。

## 指定観点の確認

### モデル読込失敗時の動画表示

`detector === null` の場合、`updateFrame()` と `render()` は黒塗りを行わず、`drawImage(this.video, ...)` で動画をCanvasへ描画します。

- `index.html:268–279`
- `index.html:292–301`

モデルCDNが利用できない場合も、Player生成後にモデル初期化エラーを捕捉し、動画操作を継続できる構造です。

### ステータス表示

以下はコード上実装されています。

- モデル読込中: `index.html:136`, `174–180`
- モデル読込成功: `index.html:408–409`
- モデル読込失敗: `index.html:412–417`
- 動画読込中: `index.html:247–260`
- 動画メタデータ読込完了: `index.html:174–187`
- 動画読込エラー: `index.html:194–196`
- `play()` 同期例外およびPromise拒否: `index.html:228–238`

### Canvasの透明／黒表示

コード上、意図された切り替えになっています。

- モデルなし: Canvasを黒塗りせず、動画をCanvasへ描画
- モデルありかつスティック表示ON: Canvasを黒塗りして骨格を描画
- モデルありかつスティック表示OFF: 動画をCanvasへ描画
- CSS上の動画背景は黒、Canvas背景は透明: `index.html:36–47`

モデル失敗時に黒いCanvasが動画を隠し続ける問題は解消されています。

### ObjectURLの解放

動画切替時には、前のObjectURLを解放しています。

- **ファイル:** `index.html`
- **行:** 247–257

```js
if (this.objectUrl) {
  URL.revokeObjectURL(this.objectUrl);
  this.objectUrl = null;
}
```

追加テストでも、2本目の動画を選択した際に1本目のObjectURLが解放されることを確認しています。

現在使用中のObjectURLは、次の動画へ切り替えるまで保持されます。これは通常の利用では妥当ですが、動画エラー時やページを長時間使った後の明示的な解放処理はありません。

### 通常時のMoveNet Thunder・骨格表示

以下の設定は維持されています。

```js
poseDetection.SupportedModels.MoveNet,
{ modelType: poseDetection.movenet.modelType.SINGLEPOSE_THUNDER }
```

- **ファイル:** `index.html`
- **行:** 404–407

`detector` が存在する場合はCanvasを黒塗りし、`estimatePoses()` 後に `drawAllPoses()` を呼ぶため、通常時の骨格描画経路も維持されています。

ただし、今回のNodeテストは `getAdjacentPairs()` が空配列で、実際の17キーポイントや骨格線を描画していません。通常時の実MoveNet検出と骨格表示は、コード上は問題ありませんが、このレビューで実ブラウザ合格とは判定していません。

## 残存指摘

### Low: 動画エラー時に再試行AnimationFrameが残る可能性

- **ファイル:** `index.html`
- **行:** 194–196、286–290
- **重要度:** Low
- **再現条件:** 動画再生状態のまま、メディアが準備完了する前に読み込みエラーが発生し、ブラウザが自動的に `paused` を `true` にしない場合

`render()` は準備未完了時にAnimationFrameを繰り返し予約します。一方、`video.onerror` はステータス更新だけで、予約済みのAnimationFrameをキャンセルしていません。

```js
this.video.onerror = () => {
  this.setStatus('動画を読み込めませんでした。対応形式を確認してください。');
};
```

この状態で `paused === false` かつ `ended === false` が残るブラウザ実装では、描画可能にならないままAnimationFrameの再試行が継続し、不要なCPU使用が発生する可能性があります。

修正案:

```js
this.video.onerror = () => {
  cancelAnimationFrame(this.animationId);
  this.animationId = null;
  this.setStatus('動画を読み込めませんでした。対応形式を確認してください。');
};
```

必要であれば、エラー時に `this.video.pause()` も行うべきです。ただし、通常のブラウザではメディアエラー時に再生が停止する可能性が高く、今回のPRの主要目的を阻害する確実な不具合とは判断しません。

## テストと限界

指定HEADで以下を実行しました。

```text
node tests/motion-phase1.test.js
```

結果:

```text
11/11 PASS
```

確認できた内容は、モデルなしの動画表示、モデル失敗時の表示、ステータス、Canvasの黒塗り回避、ObjectURLの切替解放、描画準備前の再試行、モデル読込時の二重ループ防止、`play()` 同期例外、`play()` Promise拒否です。

一方、今回実施していないため合格扱いにしていないものは次のとおりです。

- 実Chrome、Safari、Chromebook、iOS Safari
- 実動画ファイルの再生と動画エラー
- 実CDN遮断環境
- 実MoveNet Thunderのモデル取得と推論
- 実17キーポイントの骨格描画
- 実ブラウザの `readyState` 遷移
- 実ブラウザでのObjectURLメモリ挙動

### 最終判定

- **Critical:** なし
- **High:** なし。前回の描画準備前停止は解消
- **Medium:** なし。モデル完了時の二重ループと`play()`同期例外は解消
- **Low:** 動画エラー時の再試行AnimationFrame停止が明示されていない

主要な修正内容は前回指摘に対応できています。残存するLow指摘を除けば、今回の差分から新たなマージ阻害レベルの問題は確認できません。