# Claude・Cue by Manus 直接レビュー連携（承認制・初期状態は無効）

## 2026-11-11 の到達点

**このPRは外部AIへの自動送信機能の準備です。初期状態はOFFであり、Claude／Cueを実際に起動したものではありません。** PR作成・更新だけではAIを起動しません。Cue by ManusとCue OSは**別製品**です。この仕組みは**Cue by Manus**向けに公式Manus API v2を使います。

| 対象 | 公式の実行経路 | 自動依頼の条件 | 成果物 |
|---|---|---|---|
| Claude | Claude Code GitHub Action | 所有者による`/claude-review` + 明示的なフラグ + Claude Code OAuth Secret | Claudeが直接PRコメントにレビューする方式（本番未実証） |
| Cue by Manus | Manus API v2 `task.sendMessage` → `task.listMessages` | 所有者による`/cue-review` + 明示的なフラグ + Manus APIキー + 指定Cue Agent task ID | PRコメントの実行状況更新。公開テキストは別の明示的なフラグが必要（本番未実証） |

## 原則
- **通常のPR作成・更新からは両方とも絶対に起動しない。**
- リポジトリ所有者`shimamu34`による指定の**1つの正確なコマンド**だけを受け付ける。
- 実行前に現在のPR HEADとコマンド・認証情報を確認し、GitHubに予約コメントを先行記録する。
- **同じPR番号・同じHEAD・同じAIにつき最大1回**。予約後は外部AIの応答が不明でも自動リトライしない。ダブルチャージを防ぐため。
- すべてのスクリプトはGitHubの`main`から読み込む。PR差分に含まれる任意のコードを実行・編集しない。GitHubトークンはcontents: readに制限。
- mainマージ、アプリのデプロイ、学校の資料・生徒動画の外部送信は禁止。プライバシーに配慮し、Public GitHubへ生徒の個人情報や未公開資料を載せない。

## デフォルトでは外部AIが起動しない理由

両ワークフローとも`issue_comment`イベントがあっても、以下のRepository **Variables**が存在せず、または`true`でない場合は**job自体をスキップ**する。

- `ENABLE_CLAUDE_DIRECT_REVIEW` — **未設定がデフォルト**
- `ENABLE_CUE_DIRECT_REVIEW` — **未設定がデフォルト**

機能を試す際は、**APIの費用・利用枠を先に確認したうえで**、必要な方だけユーザー自身がGitHubのSettings → Secrets and variables → Actions → Variablesからtrueにする。まだ試さない場合は何も設定しない。

## Cue by Manusを接続する場合（別途承認後）

Manusの公式[Agents](https://open.manus.ai/docs/v2/agents-overview)では、CueのAgentのメインタスクに対して`task.sendMessage`でメッセージを送り、`task.listMessages`で結果を取得する方式が説明されている。

- Secret `MANUS_API_KEY`：Manus API v2への認証キー。すでに設定済みかどうかはこのPRの作業中に確認していない。
- Secret `CUE_AGENT_TASK_ID`：**対象Cue Agentのメインタスクの22文字英数字ID**。Manus APIの`agent.list`または`agent.detail`で取得した正しい対象を用いる。**デフォルトのManus IM Agent（`agent-default-main_task`）は意図しないCueへの誤送信防止のため使用禁止**。
- 2つのSecretをユーザー自身で登録した後、費用・連携先を確認し、Variable`ENABLE_CUE_DIRECT_REVIEW=true`を設定する。PR Conversationに`/cue-review`とコメントした場合にのみ**新規1依頼分**のAPI呼出しを試みる。
- 回答の追跡には対象PRのHEADを含む相関IDを利用し、**以前のCue会話の返答を今回の結果と誤認しない**。Cueには個人用のAgent記憶があるため、回答が公開リポジトリに含まれると情報漏えいのおそれがある。
- デフォルトで**Cueからの回答本文はPublic PRへ書き込まない**。PRにはAPI送信・回答確認の状態のみを記録する。
- ユーザーが技術レビュー内容の一般公開を別途許可した場合に限りVariable`PUBLISH_CUE_REVIEW_TEXT=true`を設定する。秘密情報らしき文字列の簡易マスクは行うが**完全ではない**ため、この機能の使用前に対象Cueエージェントの用途と回答範囲を確認する。
- **送信時にManusクレジットを消費する可能性がある**。ユーザーのクレジット予算やCueの利用枠は確認できていない。安易に本番テストを実行しない。
- Cueアプリ・Manus APIの具体的な認証権限やCue AgentのタスクIDが取得できない場合は利用を見送る。未確認の対象に送信してはいけない。

公式：[Manus agents API](https://open.manus.ai/docs/v2/agents-overview)、[task.sendMessage](https://open.manus.ai/docs/v2/task.sendMessage)、[task.listMessages](https://open.manus.ai/docs/v2/task.listMessages)。

## Claudeの直接GitHubレビューを接続する場合（別途承認後）

現行で使っている**通常のClaudeチャット**と、GitHub Actionsで動く**Claude Code**は別の利用経路です。ClaudeチャットのGitHub連携はリポジトリのファイル参照機能であり、PRイベントによる自動レビュー実行を意味しません。

- Anthropic公式[Claude Code Action](https://github.com/anthropics/claude-code-action)が必要。Claude GitHub Appのインストール、認証設定と本人による費用確認が必要です。
- Secret `CLAUDE_CODE_OAUTH_TOKEN`：Claude Codeサブスクリプション向けのOAuthトークン。公式[setup](https://github.com/anthropics/claude-code-action/blob/main/docs/setup.md)はPro/Maxのユーザー向け作成方法を説明している。**ユーザーがそのプランを契約しているとは確認していない**。
- 本設計は`ANTHROPIC_API_KEY`（従量課金）を使用しない。OAuthでもClaude Code利用枠の制限はあり、必ずしも追加負担なしとは保証できない。
- GitHub Secret登録・Claude GitHub Appの許可設定と必要な費用確認が済んだ後に`ENABLE_CLAUDE_DIRECT_REVIEW=true`を設定し、PRに`/claude-review`とコメントした場合だけClaude Code Actionが作動する。
- リポジトリ自体にはcontents: readの権限のみ渡し、`--disallowedTools`でEdit/Write/Bashなどを禁止する。PRコメントの追加とレビュー自体はActionの権限で実施可能。**本番のコメント生成まで実証したものではない**。
- 同じHEADへ2回依頼すると、先行予約コメントがあり追加起動しない。

公式：[Claude Code GitHub Action](https://github.com/anthropics/claude-code-action)、[setup](https://github.com/anthropics/claude-code-action/blob/main/docs/setup.md)。

## 現時点の実証済み事項と未確認事項
- `tests/test_optional_ai_review.py`による**17件の完全オフラインテスト**で、明示コマンド・所有者・Feature Flag・認証情報・現在HEAD・重複防止・短いCueプロンプト・相関ID・公開抑止を確認。
- 実際のClaude Code GitHub Actionの起動・Cueの`task.sendMessage`発行・回答回収は**一切実行していない**。
- Claudeチャット／Cueアプリの従来の無料利用を維持しながら、**費用発生リスクがある直結は利用開始時までオフにしておく**。
- すでに実運用検証済みのGitHubでの依頼文作成・ユーザー投稿結果の台帳回収は維持。今回の直結機能とは別。
