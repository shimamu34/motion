# Claude・CueへのGitHub自動引き継ぎ（パイロット）

## 目的
ChatGPT・Claude・Cue・Manus・GitHubによる共同開発の中で、レビューや修正の指示を毎回ゼロから作り直さない。**GitHubがPRの最新HEADと変更ファイルを読み、Claude／Cueに渡す短い日本語プロンプトを自動生成**する。原則として無料のGitHub Actionsのみを利用し、各AIの有料枠を勝手に消費しない。

## 実際に自動化される範囲
- `shimamu34/motion`の**所有者shimamu34が作成したPR**を対象に、main宛てのPR作成・更新・再オープンで起動。
- GitHubのPull Request metadata、変更ファイル一覧、差分の冒頭最大3,500文字を取得。
- PRのConversationに、次の情報を含むコメントを自動生成。
  - PR URL、対象HEADのコミットSHA、変更ファイル、CI確認用リンク
  - **Claudeに貼り付ける独立レビュー依頼**
  - **Cueに貼り付ける修正案作成依頼**
  - 実行状況「Claude未実行・Cue未実行」、検証されていない箇所の注意
- 同じPRに作成するコメントは**1件**。次のコミットが来たら既存のコメントを更新。
- 古いPRイベントに対して、最新HEADと一致しない場合はコメント更新を行わない。

## まだ自動化されない部分
- **ClaudeやCueへの直接送信・起動・返答の自動取得は未実装**。この会話でその2サービスに直接タスクを実行できるコネクタが確認できていないため。
- Claude・Cueにレビュー済み・修正済みと記載しない。実際のレビュー結果が届くまでは未完了。
- 変更のコミット、Manus実装、PRへのAIレビュー、mainマージ・デプロイはユーザーの別途承認に従う。
- Cueという名称の製品が複数あるため、**特定のCue APIが接続済みとは推定しない**。この仕組みは相手先を限定しない引き継ぎ資料として設計。

## 使い方
1. `motion`で通常どおりPRを作成する。**Manusの自動レビューはPR作成だけでは起動しない**（PR #4で変更済み）。
2. PRのConversationにある **「Claude / Cue 引き継ぎパケット（自動生成）」** というコメントを確認する。
3. Claudeにレビューを頼むときは「Claudeへ渡すレビュー依頼」をコピー。Cueへ修正計画を頼むときは「Cueへ渡す修正依頼」をコピー。
4. 取得できるコードや差分が限られる場合はPRのFiles changedを参照し、足りないソース・背景を補う。
5. その後、ChatGPTがレビュー／修正結果を確認し、必要な変更がある場合は別のブランチ・PRで進める。

## 安全・費用
- GitHub Actions`pull_request_target`で**main上の信頼済みスクリプトだけ**を実行。PRのソースコードはcheckoutも実行もしない。
- コメントはリポジトリ所有者のPRだけに自動作成し、GitHub APIのPRデータのみを参照。
- `GITHUB_TOKEN`以外の外部APIキーを使わない。Manus・Claude・Cue APIを呼び出さない。
- **実GitHubで確認した権限要件：** PRのIssue Comment APIはこの環境で`issues: write`のみだとHTTP 403となり、`pull-requests: write`を合わせて付与したGitHub Actions診断では201 Createdで成功。トークン権限はこれらのコメント処理だけに使用する。
- 差分抜粋ではGitHubトークンらしき文字列とメールアドレスを簡易マスク。ただし**完全な秘密情報・個人情報検査ではない**。学校・生徒の個人情報、授業動画、APIキーをPRに含めないこと。
- コメント・変更差分に含まれる文言は未信頼データ。各AIが不適切な指示を実行しない前提で利用する。
- PR HEADとイベントHEADが異なる場合は古いパケットを生成しない。

## 動作確認の範囲
- `tests/test_ai_handoff_packet.py`：GitHub APIをモックにした**11件の無料テスト**。
- 実際のPRにGitHub Actionがコメントを投稿する本番E2Eは、この仕組みをmainへマージ後のPRで初めて検証する。
- これを動作確認してもClaude／Cueへの自動送信までは完了扱いにしない。
- 将来特定のCueアプリ・Claude APIへの連携方法と費用が確認できた場合、別の承認ゲート付きタスクとして拡張する。

## 実装ファイル
- `.github/workflows/ai-review-handoff.yml`
- `.github/scripts/ai_handoff_packet.py`
- `tests/test_ai_handoff_packet.py`
- `.github/workflows/ai-handoff-tests.yml`

運用・進捗の管理先：`shimamu34/ai-workspace`のIssue #9。
