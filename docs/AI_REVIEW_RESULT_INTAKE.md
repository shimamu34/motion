# Claude・Cueレビュー結果のGitHub自動回収（運用案）

## 目的
「PR作成→Claude・Cueに渡す依頼文の自動生成」は既に実運用テスト済み。次の工程として、**返ってきたレビュー結果をGitHubの同じPRにひも付け、GitHub Actionsが最新コミットとの照合・受付状況・次の作業指示を集約する**。

本機能は**ClaudeやCueを直接起動・操作するものではありません**。AIへの依頼送信と返答の取得には、現状は各AIでのユーザー操作が必要です。

## 無料で使える手順

1. `motion`でPRを作成する。既存ワークフローが「Claude / Cue 引き継ぎパケット」をPR Conversationへ自動生成する。
2. Claudeでレビューを依頼する。公式GitHub連携が利用できる場合は、Claude側でリポジトリ／関連ファイルを選択してレビューする。**ClaudeによるGitHub直接アクセスやレビュー実施を、GitHubのパケット作成だけで成功扱いにはしない**。
3. Claudeから返答を受け取ったら、PR Conversationのコメント欄に次の形式で投稿する。**HEADの40文字SHAを現在のPRの値に置換**し、2行目以降には実際の回答を貼り付ける。

```text
/ai-result claude ここに40文字のPR_HEAD_SHA
Claudeから得た回答本文
```

4. Cueも使う場合は`/ai-result cue ここに40文字のPR_HEAD_SHA`として同様に投稿する。**Cueという名称のツール・APIは現状未特定であり、特定サービスへの直接送信を構築したとは扱わない**。
5. GitHub Actionsの`Aggregate Claude and Cue review reports (free)`が自動で起動し、PR上に「Claude・Cueレビュー結果の受付台帳」を**1件だけ**作成または更新。リンクされた原文とHEAD SHAを照合した結果を記録する。
6. ChatGPTにPR URLと「結果の確認」を依頼する。ChatGPTはGitHubに登録されたコメント・コード・CIを読んで、内容が妥当かを**独立して評価**する。Claude/Cueの結果を無検証で採用しない。

## 自動化される工程
- リポジトリ所有者`shimamu34`がPRに投稿した指定の`/ai-result`コマンドだけを受け付ける。他ユーザーのコメントは自動処理しない。
- Claude・Cue各1件ずつ、**現在のHEADに一致する最新コメントへのリンク**を集約。
- 同じPRに対する台帳コメントは増やさず更新する。
- PRコードが変われば、以前のHEADを対象とした結果は「未登録・未確認」に戻す。古い結果そのものはGitHubに残る。
- ClaudeとCueのどちらが提出済みかを記録し、次のChatGPTレビュー・安全な修正計画の引き継ぎ手順を表示。
- API呼び出しの対象はGitHubだけで、**Manus・Claude・Cueの有料APIを起動しない**。
- PRコードをチェックアウト・実行せず、main上の信頼できるPythonスクリプトだけを使用。

## 費用・プライバシー・重要な制限
- `motion`は**Publicリポジトリ**。PRコメントに貼った結果も公開されます。**生徒の氏名、顔や動画、学校の非公開情報、APIキー、パスワード、個人情報は決して貼り付けない**。
- 登録の事実はGitHubユーザーによる自己申告。**本当にClaude/Cueが実行したことや回答の真偽をプログラムは証明できない**。台帳は実際のAIレビュー完了を保証しない。
- 受付できるのはレビュー本文最大約24,000文字。大きすぎる場合、GitHub Actionsは処理を保留するため短縮して再投稿する。
- ClaudeやCueのAPIキー、外部サービスのログイン情報はこの運用では不要。
- Claudeの公式GitHub連携はGitHubのファイルをClaudeで**読み取る**手段であり、GitHub ActionsからClaudeへ無料でジョブを送信するAPIと同一ではない。
- この機能のテスト段階で実際にClaude/Cueへ依頼は送っていない。外部AIへの完全無人の送受信は**未実装**。
- mainマージ、デプロイ、Manus有料レビューの実行は自動では行わず、ユーザーの明示承認を維持する。

## テストと本番確認
- `tests/test_ai_review_result_ledger.py`：所有者制限、形式解析、旧SHAの除外、同一PRでの集約、PR更新時の無効化、Botコメント重複防止の**20件**をオフライン検証。
- `tests/test_ai_handoff_packet.py`：既存のPR依頼文に結果登録用コマンドが表示されるか等の無料テストも実施。
- 本番E2Eは、この仕組みをmainへマージ後、**個人情報を含まないダミー内容をテスト用PRに投稿して**GitHub Actionsコメントの生成／更新を確認する。
- 本番マージはユーザーの別途承認を得る。

## 関連ファイル
- `.github/workflows/ai-review-result-ledger.yml`：所有者コメントとPR更新の受付。
- `.github/scripts/ai_review_result_ledger.py`：現在のHEADと各回答の検証・台帳生成。
- `.github/scripts/ai_handoff_packet.py`：Claude／Cue用の依頼文に受付コマンドを掲載。
- `tests/test_ai_review_result_ledger.py`：外部APIをモックしたテスト。
- `.github/workflows/ai-review-ledger-tests.yml`：無料の検証ワークフロー。
