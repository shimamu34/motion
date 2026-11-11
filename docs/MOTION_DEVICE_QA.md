# motion 実機確認チェックリスト（Chromebook / Safari）

## 現在の自動検証実績（2026-11-11）
- Linux Google Chrome（骨格モデルのCDNを遮断）：実動画の再生・停止・速度・シーク・反転・動画切替など **9/9 PASS**。https://github.com/shimamu34/motion/actions/runs/42967647587
- Linux Google Chrome（本物のMoveNet Thunderを使用）：モデル初期化と推論成功。TensorFlow公式のテスト動画で**1人・17キーポイント・Canvasの骨格点描画17回**を確認。https://github.com/shimamu34/motion/actions/runs/42980628840
- Linux WebKit（Safariと近縁の描画エンジン）：別途GitHub Actionsで確認。**実機Safariと同一ではない**。
- 次の項目は**実機未確認**であり、この文書自体が合格記録ではない。

## 試す対象
- [修正版index.html](https://github.com/shimamu34/motion/blob/fix/motion-startup-resilience/index.html) をGitHubの「Download raw file」から取得し、端末のブラウザでローカルHTMLとして開く（OSやMDM設定によってはローカルHTMLの起動自体が制限される）。
- テスト動画は**生徒が映らない公開テスト素材か、許諾済み・個人情報を含まないもの**をローカルで選択する。アップロード・共有はしない。
- TensorFlowの公開テスト素材：`https://github.com/tensorflow/tfjs-models/blob/master/pose-detection/test_data/pose_squats.mp4`。学校のネットワークポリシーを優先する。

## A. Chromebook・デスクトップChrome
- [ ] ページが開き、動画を選択して再生・一時停止できる
- [ ] スライダーで任意の位置へ移動でき、左右反転・速度変更が効く
- [ ] ネットワークが許可する場合、モデル成功メッセージと骨格点が表示される
- [ ] CDN・重み取得に失敗した場合、モデル失敗メッセージが表示され、動画自体は見える
- [ ] スティック表示をON/OFFできる（実モデル成功時）
- [ ] 不明な画面停止・黒画面・再生不能にならない
- [ ] 実機の性能と再生速度（特に0.05倍）を確認し、使えない条件を記録

## B. iOS Safari
- [ ] iOSバージョンとSafariの環境を記録
- [ ] ローカルHTMLが開けるか、学校の管理端末で制限がないか確認
- [ ] MP4など端末が対応する動画を選択して読み込める
- [ ] 再生・一時停止・速度変更・シーク・左右反転の動作を確認
- [ ] 骨格モデルが正常に読み込めるか／モデルが使えない場合に動画を表示できるか
- [ ] 動画・Canvasの表示位置がずれないか、縦動画でも確認
- [ ] すぐ終了したり、動画の切替後に再生不能にならないか

## 未完了の別改善（Phase 2）
- スライダーの`seek()`は`currentTime`直後に表示更新を呼ぶため、移動先のフレームと画面がずれる可能性がある。
- `render()`の非同期推論と停止／再開の競合を避ける世代管理・ループ単一化は未実装。
- 30fps以外の動画での「1フレーム送り」精度は保証していない。
- これらは**Phase 1が本番合格したことを意味しない**。

## 記録形式
- 検証日時（任意）：
- 端末・OS・ブラウザ：
- ネットワークの概要（機密設定・SSIDは不要）：
- 検証した項目と結果（合格／不合格／未確認）：
- 再現手順（動画・個人情報・APIキーを添付しない）：
- 次の対応：
