#!/usr/bin/env python3
"""Collect owner-submitted Claude/Cue reviews in one GitHub PR ledger comment.

Does NOT contact external AIs, run PR source code, commit or merge code, or
confirm that the alleged AI actually produced submitted text.
"""
import json
import os
import re
import urllib.request

REPO = "shimamu34/motion"
OWNER = "shimamu34"
GH_API = "https://api.github.com/repos/" + REPO
MARKER = "<!-- ai-review-result-ledger:v1 -->"
PATTERN = re.compile(r"\A/ai-result[ \t]+(claude|cue)[ \t]+([0-9a-f]{40})[ \t]*\n([\s\S]+)\Z", re.IGNORECASE)
MAX_RESULT_CHARS = 24000
MAX_PAGES = 10


def parse_submission(body):
    """Recognize one exact, head-pinned result command; reject malformed ones."""
    value = (body or "").replace("\r\n", "\n")
    if len(value) > MAX_RESULT_CHARS + 120:
        raise ValueError("Result too long; paste a summary or link instead")
    match = PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError("Expected: /ai-result claude|cue <40-digit-head-sha> then new line with review text")
    role, head, result = match.groups()
    if len(result.strip()) < 10:
        raise ValueError("Review text must contain at least 10 characters")
    return role.lower(), head, result.strip()


def approved_event(event, env):
    if (env.get("GITHUB_REPOSITORY") != REPO
            or (event.get("repository") or {}).get("full_name") != REPO
            or env.get("GITHUB_REF") != "refs/heads/main"):
        return False
    typ = env.get("GITHUB_EVENT_NAME")
    if typ == "issue_comment":
        issue = event.get("issue") or {}
        comment = event.get("comment") or {}
        return (
            event.get("action") == "created"
            and bool(issue.get("pull_request"))
            and isinstance(issue.get("number"), int)
            and (comment.get("user") or {}).get("login") == OWNER
            and str(comment.get("body") or "").startswith("/ai-result ")
        )
    if typ == "pull_request_target":
        pr = event.get("pull_request") or {}
        return (
            event.get("action") in ("synchronize", "reopened")
            and (pr.get("user") or {}).get("login") == OWNER
            and isinstance(pr.get("number"), int)
        )
    return False


def github(path, method="GET", payload=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "motion-ai-review-results-v1",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(GH_API + path, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as response:
        text = response.read().decode("utf-8")
        return json.loads(text) if text else {}


def all_comments(number):
    result = []
    for page in range(1, MAX_PAGES + 1):
        values = github(f"/issues/{number}/comments?per_page=100&page={page}")
        if not isinstance(values, list):
            raise RuntimeError("GitHub comments could not be read")
        result.extend(values)
        if len(values) < 100:
            return result
    raise RuntimeError("Too many comments: cannot safely determine latest submissions")


def review_entries(comments, sha):
    """Newest owner submission for each role, pinned to the PR's current HEAD."""
    entries = {}
    previous_ledger = None
    for item in comments:
        user = (item.get("user") or {}).get("login")
        body = item.get("body") or ""
        if user == "github-actions[bot]" and MARKER in body:
            previous_ledger = item
        if user != OWNER or not body.startswith("/ai-result "):
            continue
        try:
            role, pinned, _ = parse_submission(body)
        except ValueError:
            continue
        if pinned != sha:
            continue
        if not isinstance(item.get("id"), int):
            continue
        entries[role] = item
    return entries, previous_ledger


def ledger_text(number, head, entries):
    url = f"https://github.com/{REPO}/pull/{number}"
    lines = [
        MARKER,
        "## Claude・Cueレビュー結果の受付台帳（GitHub自動集約）",
        "",
        f"- 対象PR: {url}",
        f"- 現在のHEAD: {head}",
        "- **これはユーザーがGitHubに登録した報告の集約であり、Claude/Cueの実行や出所を認証したものではありません。**",
        "- 各AIへの直接API送信やManusのタスク作成は行っていません。",
        "",
        "| 提出元として指定されたAI | 現在のHEADへの報告 | 原文 |",
        "|---|---|---|",
    ]
    for role, display in (("claude", "Claude"), ("cue", "Cue")):
        item = entries.get(role)
        if item:
            id_ = item["id"]
            lines.append(f"| {display} | ユーザー提出済み（未検証） | [PRコメント #{id_}]({url}#issuecomment-{id_}) |")
        else:
            lines.append(f"| {display} | 未登録・未確認 | — |")
    lines.extend([
        "",
        "### 次の担当者への引き継ぎ",
        "1. 現在のHEADと、リンクされた原文のコマンドに記録されたSHAが一致することを再確認する。",
        "2. ChatGPTが各レビューの根拠・実コード・CIを照合し、重要度と修正候補を整理する。",
        "3. 修正が必要なら新しい作業ブランチに限定し、PR更新・Manus有料レビュー・mainマージは別途承認を取る。",
        "",
        "### 登録方法（GitHub PR Conversation）",
        "Claudeから受け取った結果を登録する場合、次の1行に続けて改行し、回答を貼り付ける。",
        f"    /ai-result claude {head}",
        "Cueの場合は同じ形式で claude を cue に変更する。",
        "",
        "※ このリポジトリは公開されているため、**生徒・学校・個人情報、秘密鍵、未公開資料を投稿しないこと**。",
        "※ 新しいコミットでHEADが変わると、以前のSHAに紐づく回答は未登録扱いになります。",
    ])
    return "\n".join(lines)


def main():
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        event = json.load(f)
    if not approved_event(event, os.environ):
        print("SKIP: event not authorized")
        return
    event_type = os.environ["GITHUB_EVENT_NAME"]
    if event_type == "issue_comment":
        number = event["issue"]["number"]
        try:
            _, pinned_sha, _ = parse_submission(event["comment"]["body"])
        except ValueError as error:
            print(f"INVALID_SUBMISSION: {error}")
            return
    else:
        number = event["pull_request"]["number"]
        pinned_sha = (event["pull_request"].get("head") or {}).get("sha")

    pr = github(f"/pulls/{number}")
    if pr.get("state") != "open" or pr.get("merged") or (pr.get("base") or {}).get("ref") != "main":
        print("SKIP: PR is not open against main")
        return
    if (pr.get("user") or {}).get("login") != OWNER:
        print("SKIP: PR author is not repository owner")
        return
    head = (pr.get("head") or {}).get("sha")
    if not isinstance(head, str) or re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise RuntimeError("HEAD SHA invalid or unavailable")
    if pinned_sha != head:
        print("STALE: event/result SHA no longer equals PR HEAD")
        return

    comments = all_comments(number)
    entries, previous = review_entries(comments, head)
    if event_type == "pull_request_target" and previous is None:
        print("SKIP: no result ledger to update after new commit")
        return
    body = ledger_text(number, head, entries)
    if previous:
        if previous.get("body") == body:
            print("UNCHANGED: current result ledger")
            return
        github(f"/issues/comments/{previous['id']}", "PATCH", {"body": body})
        print(f"UPDATED_LEDGER: PR={number} HEAD={head} entries={list(entries)}")
    else:
        item = github(f"/issues/{number}/comments", "POST", {"body": body})
        print(f"CREATED_LEDGER: PR={number} HEAD={head} comment_id={item.get('id')} entries={list(entries)}")


if __name__ == "__main__":
    main()
