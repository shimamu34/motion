# motion Phase-1：本物のMoveNet Thunder検証結果（2026-11-11）

## 検証目的と前提
- GitHub上の実ソース `index.html`（ブランチ `fix/motion-startup-resilience`、**main未変更**）を実Chromeで実行。
- TensorFlow.js・`@tensorflow-models/pose-detection`・MoveNet Thunderを実際にCDNとモデル配信元から読み込む（モデルのモックなし）。
- データは学校・生徒の動画ではない。`tensorflow/tfjs-models`の公開テスト素材 `pose-detection/test_data/pose_squats.mp4`をGitHub Actions内で取得してWebMへ変換。検証環境外へ結果をアップロードしない。
- CI成功実行：**https://github.com/shimamu34/motion/actions/runs/42980628840**
- 実行コード：`tests/motion-real-model-chromium.cjs`
- ランナー内でブラウザを起動するため、GitHub Actionsの実行結果であり、Chromebook/iPhoneの実機測定ではない。

## 結果（5/5 PASS）
1. **M1 PASS**：実際のTensorFlow.jsとMoveNet Thunderをダウンロードし、アプリのモデル初期化ステータスが`READY`。
2. **M2 PASS**：モデルに対する`estimatePoses()`が実行され、合成WebM動画ではエラーなし・検出人数0。
3. **M3 PASS**：推論エラーがなく、結果の形状を確認。
4. **M4 PASS**：TensorFlow公式テスト動画では、推論結果は**1人・17キーポイント**。最高信頼度は**0.9280443787574768**。
5. **M5 PASS**：実モデルのキーポイントからCanvasへの**17回のarc描画呼び出し**を記録。アプリが骨格点描画に到達したことを確認。

ログ内の証拠：
```text
MODEL_INITIALIZATION: READY
REAL_MOVENET_PROBE {"created":true,"estimates":1,"poses":0,"keypoints":0,"maxScore":0,"arcs":0,"errors":[]}
OFFICIAL_TEST_VIDEO_PROBE {"created":true,"estimates":2,"poses":1,"keypoints":17,"maxScore":0.9280443787574768,"arcs":17,"errors":[]}
PASS M4: Real MoveNet detected 17 keypoints from official TensorFlow test video
PASS M5: App drew visible pose landmark arcs using real inference (not a mock)
```
- CIのスクリーンショットはrunのArtifacts `motion-real-movenet-chrome-evidence`（7日保持）から確認できる。
- テストが一時的に挿入した観測用コードは`poseDetection.createDetector`と`detector.estimatePoses`の呼出しを数え、Canvasの`arc`を数えるだけ。**本物のモデルと元のアプリロジックを使用**し、模擬推論結果は挿入していない。

## 証明できないこと
- キーポイントの**精度**、動画背景と骨格の**完全な同一フレーム同期**、低FPS動画や激しい運動での表示品質。
- ChromeOS ChromebookやiOS Safariの実機でMoveNetが使えること（実行環境はLinux headless Chrome）。
- 学校ネットワークのアクセス許可・低性能Chromebookでの速度・メモリ量。
- 長時間動作、切替直後の古い推論結果混在など、独立設計レビューのH2/H3（別段階）。
- TensorFlow公式のテスト動画は開発用の公開素材であり、学校から提供された人物動画ではない。

## 今後
- 未済：Safari/Chromebook側の検証と校内環境でのテスト。
- 未済：PRによるmain反映（PR生成時に既存のManus自動レビューが走る可能性があり、ユーザーの追加クレジット承認なしには作成しない）。
- 動画/生徒データとAPIキーをPRやIssueに貼り付けない。
