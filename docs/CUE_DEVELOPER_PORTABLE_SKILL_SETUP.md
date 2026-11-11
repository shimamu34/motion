# Cue by Manus「developer」へのGitHub共同開発Skillの受け渡し

## アカウントの境界を維持

- **Cue by Manus**：既存の`developer`を使用。凍結された旧Manusアカウントを前提にしない。
- **現在のManus**：別の有効アカウントで稼働。GitHub Secret`MANUS_API_KEY`を保持し、改変しない。
- **GitHub**：`shimamu34/motion`は公開リポジトリであり、PRコードを読み取るだけなら一般公開URLを使用できる。
- 現在の`MANUS_API_KEY`からCueの`developer`を呼び出す方式は**未成立**。APIで読取専用`agent.list`を試したが、返答に一覧情報がなく、接続先が特定できていない。
- GitHubの`ENABLE_CUE_DIRECT_REVIEW`、`ENABLE_CLAUDE_DIRECT_REVIEW`は、有料実行の可能性があるため**未設定／無効のまま維持**。Secret値やアカウント認証情報をこのファイルに書かない。

## 今回作成したもの

[Skill本文](../skills/cue-developer-motion-pr-review/SKILL.md)（GitHubのソースツリー内では`skills/cue-developer-motion-pr-review/SKILL.md`）

Cueの`developer`がPRを読み、最小差分でレビューし、GitHubの`/ai-result cue <HEAD>`形式で結果を返せるようにする手順書。**Cue本体にはまだインストールされていない**。

## 使用するまでの最小操作

1. Cue by Manusを開き、エージェント`developer`を選ぶ。
2. エージェントのSkill設定機能があれば、上記`SKILL.md`の内容を登録する。公式ManusヘルプではCueとManusのSkill設定が別であると説明している。Cue側でGitHub URLインポートができるかは**未確認**のため、インポートが出なければ内容をコピーしてカスタム指示に貼る。
3. Cue`developer`に「`https://github.com/shimamu34/motion/pull/<番号>`をSkillに従い、変更コードと現在のHEADに基づいて**読取専用**でレビュー。登録用`/ai-result cue`の文章を作成」と依頼する。
4. Cueの回答を確認したうえで、問題がなければGitHub PRのConversationに登録用テキストを投稿する。既存GitHub Actionsの結果回収ワークフローが最新HEADとの一致を調べ、Claude/Cue結果台帳を更新する。
5. Cue自身がコメント投稿できるかはCue側のGitHub権限次第。**Cueから直接GitHubへ投稿できると確認できるまで、利用者本人による投稿**を前提にする。

## 自動化の限界

- **自動化済み**：PR作成時の指示パケット生成、ユーザーがCueの回答をGitHubに登録した後のSHA確認・台帳更新。
- **今回準備した部分**：Cue developerに伝えるレビュー手順の再利用（Skill）。
- **未実装**：GitHubからCueへ自動でレビュー依頼する処理、CueからGitHubへの無人コメント投稿、返信の自動取得。
- Cueが独自のメールアドレスやスケジュール機能を持つことは公式に説明されているが、**GitHub PR更新をCueに無人転送する公式な接続は、現在のアカウント構成で確認できていない**。ユーザーの承認なしにメール転送や定期実行を作らない。
- 公開PRに個人情報・非公開の授業資料・生徒動画や秘密情報を投稿しない。

## 公式根拠

- [ManusのSkill共有とCueでのSkill利用（公式日本語ヘルプ）](https://help.manus.im/ja/articles/14753565-manus-%E3%81%A7-skill-%E3%82%92%E5%85%B1%E6%9C%89-%E4%BD%BF%E7%94%A8%E3%81%99%E3%82%8B%E3%81%AB%E3%81%AF)
- [Cue by Manusの機能（公式）](https://help.manus.im/ja/articles/17190150-manus-2-0-%E3%81%AE%E6%96%B0%E6%A9%9F%E8%83%BD)
- [ManusのAgents API仕様](https://open.manus.ai/docs/v2/agents-overview)

## 次の確認ゲート

GitHubにSkillを配置した後、ユーザーがCue`developer`のSkill設定画面を開き、**CueでSkillを追加する操作が使えるかを1回確認**する。確認前に「CueにSkillを適用済み」「完全自動化済み」とは主張しない。
