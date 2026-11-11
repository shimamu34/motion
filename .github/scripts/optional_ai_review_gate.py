#!/usr/bin/env python3
"""Cost-gated, one-request-per-PR-HEAD preflight for Cue or Claude Code.

This preflight never calls any AI service. It validates a GitHub owner's exact
command, current PR HEAD, explicit repository feature flag, secret presence,
and writes a GitHub comment reservation BEFORE AI execution.
"""
import json
import os
import re
import urllib.request

REPO = "shimamu34/motion"
OWNER = "shimamu34"
API = f"https://api.github.com/repos/{REPO}"
MODES = {"cue": "/cue-review", "claude": "/claude-review"}


def valid_event(event, env, mode):
    issue, comment = event.get("issue") or {}, event.get("comment") or {}
    return (
        mode in MODES
        and env.get("GITHUB_EVENT_NAME") == "issue_comment"
        and env.get("GITHUB_REPOSITORY") == REPO
        and env.get("GITHUB_REF") == "refs/heads/main"
        and (event.get("repository") or {}).get("full_name") == REPO
        and event.get("action") == "created"
        and bool(issue.get("pull_request"))
        and isinstance(issue.get("number"), int)
        and (comment.get("user") or {}).get("login") == OWNER
        and (comment.get("body") or "").strip() == MODES[mode]
    )


def marker(mode, number, sha):
    if mode not in MODES or not re.fullmatch(r"[a-f0-9]{40}", sha or ""):
        raise ValueError("Invalid AI mode or SHA")
    return f"<!-- direct-ai-review:v1:{mode}:pr={number}:head={sha} -->"


def github(path, method="GET", payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "motion-approved-optional-ai-bridge",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, headers=headers, method=method, data=data)
    with urllib.request.urlopen(req, timeout=40) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def find_reservation(number, tag):
    for page in range(1, 11):
        comments = github(f"/issues/{number}/comments?per_page=100&page={page}")
        if not isinstance(comments, list):
            raise RuntimeError("Cannot safely inspect PR comments")
        for c in comments:
            if (c.get("user") or {}).get("login") == "github-actions[bot]" and tag in (c.get("body") or ""):
                return c
        if len(comments) < 100:
            return None
    raise RuntimeError("Too many PR comments; fail closed")


def format_note(mode, number, sha, stage, detail=""):
    return "\n".join([
        marker(mode, number, sha),
        f"## {mode.upper()} review — approval-gated",
        f"- PR: https://github.com/{REPO}/pull/{number}",
        f"- 対象HEAD: "+ chr(96) + sha + chr(96),
        f"- 状態: **{stage}**",
        f"- 備考: {detail[:250]}",
        "- これは依頼の予約・監査記録です。レビュー成功・課金額は別途確認してください。",
        "- 同じコミットへの自動再依頼を防ぐため、予約後は失敗しても再起動しません。",
        "- mainへのマージ、アプリの編集、デプロイはしません。",
    ])


def gate(event, env, mode):
    """Return a safe dispatch tuple or None; never call an AI API here."""
    if not valid_event(event, env, mode):
        return None
    if env.get("DIRECT_REVIEW_ENABLED", "").lower() != "true":
        print("DISABLED: repository setting not explicitly enabled")
        return None
    if mode == "claude" and not env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        print("NO_CREDENTIAL: Claude Code subscription token absent")
        return None
    if mode == "cue" and (
        not env.get("MANUS_API_KEY")
        or not re.fullmatch(r"[A-Za-z0-9]{22}", env.get("CUE_AGENT_TASK_ID") or "")
    ):
        print("NO_CREDENTIAL: Manus key or valid 22-character Cue agent main task ID absent")
        return None
    number = event["issue"]["number"]
    pr = github(f"/pulls/{number}")
    if (pr.get("state") != "open" or pr.get("merged")
            or (pr.get("base") or {}).get("ref") != "main"
            or (pr.get("user") or {}).get("login") != OWNER):
        print("SKIP: PR must be open, owner-authored and based on main")
        return None
    sha = (pr.get("head") or {}).get("sha", "")
    tag = marker(mode, number, sha)
    existing = find_reservation(number, tag)
    if existing:
        print(f"ALREADY_RESERVED: PR={number} SHA={sha} comment={existing['id']}")
        return None
    fresh = github(f"/pulls/{number}")
    if fresh.get("state") != "open" or (fresh.get("head") or {}).get("sha") != sha:
        print("STALE_PR: review command no longer matches current HEAD")
        return None
    note = format_note(mode, number, sha, "RESERVED_BEFORE_AI_REQUEST",
                       "ユーザーの明示コマンドから1件だけAI依頼を予約。まだAIを呼んでいません。")
    comment = github(f"/issues/{number}/comments", "POST", {"body": note})
    if not isinstance(comment.get("id"), int):
        raise RuntimeError("Reservation comment failed; no AI request was made")
    print(f"RESERVED: provider={mode} pr={number} head={sha} comment={comment['id']}")
    return {"pr": number, "sha": sha, "comment_id": comment["id"]}


def main():
    mode = os.environ["REVIEW_PROVIDER"]
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as file:
        event = json.load(file)
    selected = gate(event, os.environ, mode)
    if not selected:
        return
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        handle.write("should_run=true\n")
        for key, value in selected.items():
            handle.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
