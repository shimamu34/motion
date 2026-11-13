# motion：Chromebook・実ブラウザ・MoveNet Thunderの受入テスト

## 目的

GitHub Actionsのモックテストだけでは証明できない「本当の端末で動画が再生できるか」「MoveNet Thunderが読み込めるか」を、**個人情報のないテスト動画**で確認する。

- 診断ページ: `tests/browser-device-smoke.html`
- 本番アプリ: `index.html`
- 想定公開URL: `https://shimamu34.github.io/motion/tests/browser-device-smoke.html`（PRを承認マージし、Pages配信が終わった場合のみ利用可。URLの実際の配信可否は確認を要する）
- この診断ページは**カメラを起動しない**。現行のmotionアプリ自体が端末上の動画ファイルを入力する構成であり、ライブカメラ・web遅延ツールの確認とは別。

## 準備

学校・生徒・教員の非公開情報や個人の顔を含まない、公開しても問題のない短いMP4テスト動画を準備する。外部送信は行わない設計だが、ライブラリとモデルの取得でネットワークを使用する。

## 既存のテスト実績（重複検証を避ける）

2026-11-11の開発ブランチ `fix/motion-startup-resilience` では、別途以下の実ブラウザ検証が記録されている。いずれも**当時のテスト対象コミット**についての成功であり、現在の公開mainや学校Chromebookでの動作を無条件に保証しない。

- [実Chromiumでモデル読込失敗時の動画操作9項目を確認したActions](https://github.com/shimamu34/motion/actions/runs/42967647587)：success。
- [実MoveNet ThunderのChrome検証Actions](https://github.com/shimamu34/motion/actions/runs/42980628840)：success。GitHub Issue #9には1人・17キーポイント検出の報告が残っている。
- [Linux WebKitのフォールバック検証Actions](https://github.com/shimamu34/motion/actions/runs/42981091957)：success。iOS Safari実機とは異なる。
- [手動実機確認用ZIPの生成Actions](https://github.com/shimamu34/motion/actions/runs/42982100057)：success。ユーザーはキットの操作について「全て動いた」と回答しているが、端末名・ブラウザ・実MoveNet検出・動画と骨格の同期は確定していない（[Private記録Issue #9](https://github.com/shimamu34/ai-workspace/issues/9)）。

**今回追加する診断ページの価値は、動画をアップロードせず、通常のHTTPSブラウザから現行アプリと同じライブラリを直接検証でき、結果を非個人情報のJSONとして共有できること**。以前の成果を無かったことにして再実装しない。

## Chromebookでの手順

1. ChromeのHTTPSページから診断ページを開く。初回はモデルをまだ読み込まない。
2. 「動画を選択」で安全なMP4動画を選び、動画の映像が表示されるか確認。診断`video_decoding`がPASSか確認。
3. 再生／停止、中間シーク、約1フレーム進む、速度0.5倍／2倍、左右反転を順に操作し、動画の見た目・操作と`PASS`の両方を確認する。短い動画や末尾でフレーム送りができない場合は十分な長さの動画で再試行。
4. 「MoveNet Thunderを読み込む」を1回押し、ダウンロード後に`movenet_thunder_load`がPASSか確認。
5. 実際に人が映っている公開可能なテスト動画を、**全身が映る明るいフレームで一時停止**して「現在の映像で姿勢推定」を押す。`movenet_thunder_inference=PASS`と`PosesFound`は姿勢候補が返されたことを示す。**`pose_visualization=PASS`なら水色の骨格線と白い関節点がその停止画面に表示される**。`NoPosesInFrame`は計算成功でも人物未検出なので、その位置で骨格線が出ないのは正常。再生・シーク後は再度推定する。
6. 「診断結果をコピー」でJSONを取得。ファイル名・画像・骨格座標・ユーザーエージェントは含めない。必要に応じてChatGPTへ結果を提示する。
7. **本番の`motion/index.html`でも同じ動画**を選ぶ。モデル読込表示、動画再生・停止、シーク、速度、1フレーム前後、左右反転、スティックピクチャーと実映像の切替、および映像と骨格の同期を目視で確認する。

## 判定基準

| 項目 | 合格 | 未合格／未確認 |
|---|---|---|
| 動画デコード | 映像が見え、再生と停止が安定する | 黒画面・音声のみ・CodecError等 |
| 動画操作 | シーク・速度・コマ送り・左右反転が効く | UIの値だけ変わるが映像が追従しない |
| MoveNetモデル | `movenet_thunder_load=PASS` | CDN/モデル転送先403・メモリ不足・モデル初期化失敗 |
| 実推定 | `movenet_thunder_inference=PASS` と適切な人物の検出 | `NoPosesInFrame`は計算成功でも人物0人。モデル動作成功と骨格検出成功を分ける |
| 診断上の骨格描画 | `pose_visualization=PASS`、静止動画に水色線・白い点が一致 | `NO_POSE`は未検出、`NO_VISIBLE_SKELETON`は有効点不足。描画位置も目視確認する |
| 本番との一致 | 本番index.htmlの骨格と動画が一致 | 診断PASSだけで本番PASSとは扱わない |

## 範囲・費用・安全

- 診断ページは`<input type=file>`と`URL.createObjectURL`で動画をローカルに読み込む。動画アップロード、通信でのフレーム送信、外部保存は行わない。モデルライブラリと重みのダウンロード通信のみ。
- GitHub Actionsの`test_browser_device_smoke.py`はHTMLの構造・ライブラリ・非送信設計を静的に確認するオフラインテストで、**実機・姿勢推定の成功ではない**。
- 使用枠は端末とネットワークの通常利用だけ。Manus・Cue・Codex・Claudeや有料AI APIは起動しない。
- 実機検証の未完了箇所は「未確認」と記録する。Chromebookで動作しない場合は、ブラウザ・モデル・動画コーデックのどれかを切り分けてから修正する。

## Chromebookからの実診断（2026-11-13、ユーザー報告）

端末のChromeで、**動画デコード・再生停止・MoveNet Thunderモデル読込・姿勢推定関数の実行がPASS**。ただし`movenet_thunder_inference_detail=NoPosesInFrame`のため人物は検出できず、シーク／フレーム送り／速度／左右反転は未確認。学校Chromebookでの**骨格描画合格・本番アプリの骨格同期合格にはできない**。

旧診断ページ`motion-local-device-smoke-v1`には`canvas`や骨格描画命令がなく、仮に`PosesFound`になっても画面に骨格を描画しなかった。よって「線が表示されなかった」事実は描画故障の証拠ではない。

提案する改良は診断ページだけに`canvas`レイヤーを付け、同じ停止フレームでMoveNetの17点のうち信頼度0.3以上の関節点を白で、つながる関節を水色で描く。**動画の再生やシークで骨格を消し、再推定が必要**と案内する。診断結果JSONは関節座標・画像・ファイル名・端末情報を収集しない。改善版公開後のChromebook実機テストは別途必須。
