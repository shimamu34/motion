# ManusによるPRレビューの運用手順（2026-11-11改訂案）

## 目的
以前の`manus-pr-review.yml`には、PR作成・更新時に毎回Manus APIを起動する設計と、PR本文＋長い差分を送る設計がありました。PR #2でHTTP 400エラーが2回発生しました。入力長の超過が原因の有力仮説ですが、当初のエラーレスポンスが残されていないため断定しません。

本改修後、PR作成・更新だけではManusへ**一切依頼しません**。**GitHubオーナーによる明示的な1回のレビュー指示**だけをトリガーにします。

## レビューを実行する操作
1. GitHubで対象のPRを開く。
2. PRの**Conversation**タブのコメント欄に、正確に`/manus-review`と入力して**Comment**する。
3. GitHub Actionsの`Manus AI PR Review (approval required)`が起動し、対象PRのHEADを読み、Manus APIへ短いレビュー指示を1回だけ送る。
4. PRコメントに自動的に投稿される`REQUEST_RESERVED`または`DISPATCHED`を確認する。レビューが完了すると、その**同じコメント**がレビュー内容とManus APIの報告使用量で更新される。
5. コメントから結果と確認できなかった項目を見て、GitHubのCI結果と照合する。**Manusが終了してもmainへのマージは自動実行しません**。

**重要**：コマンドを送れるのはリポジトリ所有者`shimamu34`だけ。コードや他ユーザーのPRコメントに同じ文字列が含まれても起動しません。

## 無駄なクレジット消費を防ぐ仕組み
- PRを開く（`opened`）・内容を書き換える（`synchronize`）・再オープン（`reopened`）だけでは**起動しません**。
- 同じPR番号・同じHEAD SHAに対し、GitHub Actions botのレビュー予約コメントを**API呼出しより前**に記録。再度コマンドを送っても**重複を検出してスキップ**。
- HEADがコメント受理後に変化した場合は、Manusへの送信前に再確認して中止。
- リポジトリごとのconcurrencyで同時レビューを直列化し、`cancel-in-progress: false`として途中で有料タスクを強制再起動しない。
- ManusへはPR URL、HEAD SHA、短い確認指示、**差分冒頭3,600文字まで**を送信。プロンプト全体は**6,200文字以下**。全差分をManusが読めない場合はレビュー範囲の制限を報告させる。
- HTTP 400などの場合、秘密情報を除外したコード・短いエラー情報をPRコメントに記録。**同じSHAへの自動再試行はしない**。
- ManusのタスクIDが発行されたら直ちにPRの予約コメントを更新。続く監視やコメント更新に失敗しても再作成しない。
- 旧APIキーはGitHub Actionsの`MANUS_API_KEY` Secretを利用。コードとレビューコメントにキーを直接埋め込まない。
- レビュー対象のPRコードは**実行せず、GitHub APIでデータとして読む**。アプリのコード・main・デプロイをManusに変更させない。

## HEADを修正した後の再レビュー
HEADが新しいコミットに変化した場合は、再度`/manus-review`コメントを送ることで、その新HEADについて**新しいレビュー1件**を依頼できます。これは追加のManusクレジットを使用し得るため、毎回のコマンド投稿が明示承認に相当します。

## 障害時の対応
- **PRコメント`REQUEST_RESERVED`のまま**：Actionsログを確認。課金が発生したか不明な場合は同じHEADで再試行しない。
- **`TASK_CREATION_UNCONFIRMED`**：Manusにタスクが作成されたか不明なため、自動再試行は禁止。タスク一覧・ログで確認してから必要なら人手で再依頼する。
- **`MANUS_STATUS_UNCONFIRMED`**：レビューが長引いた、または取得失敗。記載されたtask IDからManusの状態を確認する。
- **同じHEADで再レビューがどうしても必要な場合**：Manusの課金履歴を確認してから、オーナーが以前のGitHub Actions bot予約コメントを削除し、新たに`/manus-review`を投稿する。**誤課金防止のため、通常は行わない**。
- **レビュー結果にCriticalやHighの指摘**：PRのコードを別ブランチで直して検証し、追加レビューは再承認。mainへ直接マージしない。

## 検証と制限
- 静的・単体テストは`python3 -m unittest discover -s tests -p 'test_manus_pr_review.py' -v`で実行。**実際のManus APIを使わず**、認証、権限、重複防止、入力長、API失敗時の制御を確認。
- **本改修の本物のManus APIを使った本番動作テストは別途承認制**。GitHub Actionsで16件のオフラインテストが通っても、API呼出し・コメント書込みまで本番で確認されたわけではありません。
- Manus連携が対象PRのコード全体にアクセスできなければ、指定された差分冒頭のみのレビューとして限界を表示すること。要件・テスト・チェックはChatGPT等が独立に判断する。
- GitHub Actionsでの既存PRに残った過去の赤いチェックは、コードだけ変更しても自動で消えるわけではありません。今回のワークフロー置換は**今後のPRに適用**されます。

## 変更対象
- `.github/workflows/manus-pr-review.yml`：承認されたコメントだけをトリガーとする
- `.github/scripts/manus_pr_review.py`：Manusとの安全なAPI連携と二重起動防止
- `tests/test_manus_pr_review.py`：外部APIを使わない検証
- `.github/workflows/manus-review-guard-tests.yml`：事前検証用CI

関係する障害記録：[motion Issue #3](https://github.com/shimamu34/motion/issues/3)
