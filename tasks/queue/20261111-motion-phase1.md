# Manus Phase 1: 骨格モデル失敗時の動画操作維持

- Task ID: 20261111-MOTION-PHASE1
- Status: READY
- Assigned to: Manus
- Created by: ChatGPT
- Created: 2026-11-11
- Approval required: No
- Target repository: shimamu34/motion
- Target branch: fix/motion-startup-resilience
- Allowed source file: index.html
- Base source blob SHA: feaa7714af479d88f5860f017343dbc56a29e2ac
- Result: tasks/runs/20261111-motion-phase1-manus.md

## 目的
学校のCDN・MoveNetモデル読込に失敗した場合も、運動分析アプリのローカル動画再生と停止、速度調節、シーク、左右反転などの基本操作が可能になるように改善する。事前にClaudeが独立レビューし、ChatGPTが実装範囲を絞った最初の小さな修正。

## 実装してよい変更
- 原則として対象ブランチのindex.htmlだけに変更を加える。
- MoveNetのモデル読み込みより前にプレーヤーの基本イベントを初期化し、try/catchでモデル取得失敗を処理する。
- モデルが取得できなければ推論をスキップし、日本語でモデルが使えないことを画面に表示する。
- **前面canvasが黒く動画を覆わないこと**。モデルなしでも動画そのものを見られ、速度・シーク・再生・停止・反転が動くようにする。
- CDN全体が未読み込みでposeDetectionが未定義の場合も操作不能にならないこと。
- video.onerror・play()のPromise拒否・動画切替での旧Object URL解放を扱う。
- モデル取得が成功した場合は現行MoveNet Thunderのスティック表示・動画と骨格の重ね合わせ・速度・反転などを維持する。
- セキュリティ、プライバシー、学校の端末への影響を考え、外部への動画アップロード・個人情報転送を追加しない。

## 今回変更してはいけない箇所・操作
- index.htmlのシークと非同期推論ループの大規模改修やフレーム単位の同期改善（第2段階の別タスク）。
- 全体UIの再設計、ライブラリ変更、モデル置換、FPS変更。
- main、他のブランチ、他リポジトリ、GitHub Actionsの設定ファイル、秘密情報。
- GitHub PR作成、マージ、デプロイ、外部公開、破壊的変更。
- 生徒・学校・保護者の個人情報や実際の生徒動画の取得・保存・共有。

## 成果条件・報告
- [ ] モデル取得失敗時、動画が画面上に見える状態で基本操作可能。
- [ ] 正常読込時、従来の動画・骨格表示が維持される。
- [ ] 再生失敗・非対応動画に日本語ステータスが出る。
- [ ] 旧URLの後処理が行われる。
- [ ] ソース変更対象はindex.htmlのみ。
- [ ] 修正前後のGitコミットSHA、差分要約、確認したテスト、実機未確認事項を報告。
- [ ] 書込み権限がない場合はファイルを書き込んだと主張せず、完成版index.htmlを最終回答のコードブロックで返す。

## 追加条件
- 依頼者はManusの1タスク実行とクレジット消費を2026-11-11に承認している。
- 処理内容はChatGPTによる後続の独立検証を受けるまで完成扱いしない。
- PR作成に伴う追加のManusレビュー費用は承認していない。
