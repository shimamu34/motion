# Manusのmotion書き込み権限・最小実装テスト

- Test ID: MOTION-MANUS-WRITE-2026-11-11
- Status: DONE
- Scope: このファイル1件への編集のみ
- Project: shimamu34/motion
- Branch: feature/manus-write-smoke-2026-11-11

## テスト時に実装者がする作業

- 指定ブランチのこのファイルを読み取る。
- 上記の `- Status: PENDING` を `- Status: DONE` に変更する。
- このファイルの末尾に `- Verification: Manusが指定ブランチに変更をコミットした` を1行追加する。
- 同じブランチにコミットし、変更ファイルとコミットSHAを報告する。
- 他のファイルを編集しない。main、PR本文、設定、Secrets、デプロイを変更しない。

## 判定基準

GitHub上の実ファイル、変更コミット、差分をChatGPTが独立に照合する。
Manus自身の完了報告だけでテスト合格とはしない。
これは実際のアプリ機能修正を伴わない安全な書き込み確認である。
- Verification: Manusが指定ブランチに変更をコミットした
