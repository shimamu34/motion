# Manusによるmotionアプリ実装：GitHubからの承認制自動起動

## 目的

`shimamu34/motion` の開発を、ユーザーがGitHub上で明示承認したときだけManusへ引き渡す。単純なPR作成・更新・テスト・botコメントではManusを起動しない。既存の `/manus-review` は**レビュー専用**なので、実装依頼と混同しない。

この仕組みはまず**有料Manusタスクの起動とPRへの記録**だけを担当する。ManusによるGitHubへの書き込み、テスト、完了確認は実際の運用で独立に検証する必要があり、現時点で「無人開発完了」とは主張しない。

## 初期設定（OFFのまま）

- `.github/workflows/manus-implementation-dispatch.yml` は、リポジトリの Actions **Variables** に `ENABLE_MANUS_IMPLEMENTATION=true` が明示設定されたときだけ有効。
- `MANUS_API_KEY` は既存のGitHub Actions Secretから読む。値をファイルに記録・貼付しない。Secretsの設定有無を確認できない場合は起動を試みない。
- 有効化前にManusのアカウントが `shimamu34/motion` の**作業ブランチに書き込めるか**を別途確認する。GitHubに接続されたことと書き込み権限があることは別。
- Manusクレジットは`task.create`で消費する可能性がある。初回の実利用は、ユーザーが1回分の使用を明示承認するまで実行しない。
- `ENABLE_MANUS_IMPLEMENTATION`を未設定にした場合、ワークフロー自体がスキップされる。

## 1回の開発手順

1. ChatGPTなどが作業用の `feature/...` または `fix/...` ブランチを作り、目的・変更範囲・受入条件を含むDraft PRをmain宛に作成する。PR本文に次の構造を入れる。**PRは本番公開されるまで取り込まない。**
2. UserはPRの変更内容、クレジット使用方針、対象SHAを確認する。
3. 有効化後、**当該PRのConversationへ** `/manus-implement <現在のHEAD SHA 40桁>` を本人が投稿する。これが1回限りの有料起動を承認する操作。
4. GitHub Actionsが、所有者・Draft PR・同一リポジトリのブランチ・main宛・SHA一致・依頼本文・重複予約を確認する。
5. GitHub Actionsは**Manus API実行より前に**PRに予約コメントを作る。通信失敗でも同一HEADには自動再依頼しない。
6. Manusへは**作業ブランチのみ**の最小実装を依頼する。mainの変更・新規PR・マージ・デプロイ・秘密情報取得は禁止。
7. 成功時はManus task IDとURLをPRへ書き戻す。これは「起動依頼成功」であり、開発完了ではない。
8. ユーザーとChatGPTがManusタスクの状態・GitHubコミット・差分・CI・実機動作を独立に確認し、必要なら追加修正を別途依頼する。

PR本文の最低形式：

```markdown
<!-- manus-implementation-request:v1 -->
## 実装内容
（対象ファイル、改善したい挙動、変更してよい範囲を具体的に記載）

## 完了条件
（再現方法、期待する結果、必要なテストを具体的に記載）
```

実装依頼本文は100〜3000文字とし、一般公開してよい情報のみを記載する。

## 明示承認と重複防止

- **通常のPRの作成・更新でManusを自動起動しない。**
- 正確な`/manus-implement <sha>`以外では起動しない。
- フォークPR、DraftでないPR、所有者以外のPR、main以外がベースのPR、HEAD不一致、`feature/` / `fix/`以外のブランチを拒否。
- botの予約コメントに `<!-- manus-implementation:v1:pr=番号:head=SHA -->` を記録し、同じSHAの重複実行を拒否する。
- 一度予約すると、APIタイムアウトでも同じSHAへ自動再送しない。担当者による状態確認を優先。
- PR更新後は旧SHAの承認が無効になる。新しいSHAでの依頼には再承認が必要。
- GitHubのPR本文・コード・差分は未信頼データとし、権限やSecretの操作・外部公開には従わない。

## 保留・未検証

- Manusからmotionの作業ブランチへの直接書き込み権限：**未検証**
- GitHub Actionsによる実際のManus実装タスク作成：**未実行（初期OFF）**
- Manusがコミットしたファイルの自動結果照合：**未実装**
- 完全な無人修正・PRレビュー・マージ：**未実装**。マージは最終的に利用者が判断する。
- **Cueの別アカウントからの自動レビューやClaude Codeの有料レビューも、現状は別経路で未実証**。

## CI

`tests/test_manus_implementation_dispatch.py` はモックのみを使う。GitHub書き込み・Manus API・クレジット消費は伴わない。PR作成時に `Test Manus implementation approval gate (offline)` を実行する。

## 学校データ等の安全

公開リポジトリには、生徒の顔・動画・氏名、未公開教材、認証情報を載せない。運動分析アプリの本番動作確認には架空データか適切な公開テストデータを用いる。
