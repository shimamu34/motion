# motion Phase-1：Linux WebKitブラウザエンジン確認（2026-11-11）

## 実行条件
- **対象:** `fix/motion-startup-resilience` の実際の `index.html`
- **環境:** GitHub Actions ubuntu-24.04でPlaywright WebKit（ヘッドレス）を使用。
- **重要:** **iPhone/iPadのSafari実機ではない**。同じWebKit系でもOS、動画デコーダ、権限、GPU、メモリなどの違いがある。
- **テスト動画:** 端末・学校・生徒の映像ではなく、CI内で生成した単色のH.264/MP4。
- **ネットワーク:** TensorFlowのCDNスクリプトを意図的に遮断（モデル不在のフォールバック検証）。実MoveNetのWebKitでの推論は**未確認**。
- **成功したCI:** https://github.com/shimamu34/motion/actions/runs/42981091957
- **確認コード:** `tests/motion-webkit-fallback.cjs`

## 実WebKitエンジンでの結果（7/7 PASS）
1. WK1：モデルのCDNを遮断した状態でもアプリの基本操作が初期化される
2. WK2：ローカルH.264/MP4動画をデコードできる
3. WK3：動画を実際に再生し、再生時刻が進む
4. WK4：再生・一時停止・速度選択が反映される
5. WK5：左右反転とスライダーシークが動作する
6. WK6：別のテスト動画へ切り替えられる
7. WK7：ブラウザページの未捕捉JavaScript例外がない

## 最初の実行の失敗理由
- https://github.com/shimamu34/motion/actions/runs/42980953497 はPlaywright 1.56.1とubuntu-26.04のWebKitの互換性不足で、ブラウザ起動前に失敗。
- `runs-on: ubuntu-24.04`に固定して再実行し、全7件合格。アプリコードを変更して直した問題ではない。

## 他の検証と残り
- Chrome実動画＋骨格モデルなし：9/9 PASS。
- Chrome本物MoveNet Thunder＋TensorFlow公式テスト動画：**1人・17キーポイント・描画17回**、M1〜M5 PASS。
- Linux WebKit・モデルなし：7/7 PASS。
- **実機のChromebook/iOS Safari、WebKitの本物MoveNet、学校のネットワークでのモデル重み取得、厳密なシーク・骨格同期（Phase 2）は未検証。**
- これらが未確認のため、学校の本番端末での総合合格判定は行わない。
- PR作成・main変更・追加のManus起動は行っていない。
