#!/usr/bin/env python3
"""Reconcile already-dispatched Manus PR tasks without creating AI tasks.

Only monitors bot reservations on open motion PRs. Stopping does NOT mean
code review passed; a changed HEAD is evidence of a branch change, not of
the actor's identity, code quality, or acceptance criteria.
"""
import json
import os
import re
import urllib.parse
import urllib.request

from manus_implementation_dispatch import REPO, github, reservation_marker, SHA

BOT = "github-actions[bot]"
ACTIVE = {"DISPATCHED_NOT_VERIFIED", "RUNNING"}
STOPPED = "STOPPED_RESULTS_NEED_REVIEW"
MARKER_RE = re.compile(r"<!-- manus-implementation:v1:pr=([0-9]+):head=([0-9a-f]{40}) -->")
TASK_RE = re.compile(r"Manus task ID: ([A-Za-z0-9]{5,80})")
STATE_RE = re.compile(r"- 状態: \*\*([A-Z_]+)\*\*")
MAX_OPEN_PRS = 100
MAX_COMMENT_PAGES = 10


def extract_task(comment, expected_pr):
    if not isinstance(comment, dict) or (comment.get("user") or {}).get("login") != BOT:
        return None
    text = comment.get("body")
    if not isinstance(text, str):
        return None
    marker = MARKER_RE.search(text)
    task_id = TASK_RE.search(text)
    state = STATE_RE.search(text)
    if not marker or not task_id or not state or state.group(1) not in ACTIVE:
        return None
    if int(marker.group(1)) != expected_pr:
        return None
    if not SHA.fullmatch(marker.group(2)):
        return None
    if type(comment.get("id")) is not int:
        return None
    return {"comment_id": comment["id"], "sha": marker.group(2),
            "task_id": task_id.group(1), "state": state.group(1)}


def read_open_prs():
    prs = github(f"/pulls?state=open&per_page={MAX_OPEN_PRS}")
    if not isinstance(prs, list) or len(prs) >= MAX_OPEN_PRS:
        raise RuntimeError("Open PR listing incomplete; refusing partial audit")
    return [pr for pr in prs if (pr.get("user") or {}).get("login") == "shimamu34"
            and (pr.get("base") or {}).get("ref") == "main"]


def read_comments(number):
    results = []
    for page in range(1, MAX_COMMENT_PAGES + 1):
        items = github(f"/issues/{number}/comments?per_page=100&page={page}")
        if not isinstance(items, list):
            raise RuntimeError("PR comments listing incomplete")
        results.extend(items)
        if len(items) < 100:
            return results
    raise RuntimeError("Too many comments: refusing a partial audit")


def manus_detail(task_id):
    if not re.fullmatch(r"[A-Za-z0-9]{5,80}", task_id):
        raise ValueError("Malformed Manus task ID")
    key = os.environ.get("MANUS_API_KEY")
    if not key:
        raise RuntimeError("Manus API key absent; cannot monitor existing tasks")
    uri = "https://api.manus.ai/v2/task.detail?task_id=" + urllib.parse.quote(task_id, safe="")
    req = urllib.request.Request(uri, headers={
        "x-manus-api-key": key,
        "User-Agent": "motion-manus-implementation-monitor",
    })
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.loads(response.read().decode("utf-8"))


def outcome_status(detail, current_sha, original_sha):
    task = detail.get("task") if isinstance(detail, dict) else None
    if not isinstance(task, dict):
        return "UNKNOWN"
    status = task.get("status")
    if status == "stopped" and not task.get("has_running_background_jobs", False):
        return "STOPPED_PR_CHANGED_NEEDS_REVIEW" if current_sha != original_sha else "STOPPED_NO_CHANGE_NEEDS_REVIEW"
    if status in {"waiting", "error"}:
        return "WAITING_NEEDS_ATTENTION" if status == "waiting" else "ERROR_NEEDS_ATTENTION"
    return "RUNNING"


def note_for(task, number, status, current_sha):
    marker = reservation_marker(number, task["sha"])
    task_id = task["task_id"]
    return "\n".join([
        marker,
        "## Manusアプリ実装：自動状態確認（内容審査ではありません）",
        f"- PR: https://github.com/{REPO}/pull/{number}",
        f"- 承認時HEAD: {task['sha']}",
        f"- 現在のHEAD: {current_sha}",
        f"- Manus task ID: {task_id}",
        f"- Task: https://manus.im/app/{task_id}",
        f"- 状態: **{status}**",
        "- Manusの作業停止はコード完成や実装主体を証明しません。",
        "- 差分、テスト結果、権限、要求への適合性を独立に確認してください。",
        "- 自動マージ、デプロイ、新しいManusタスク作成はしていません。",
    ])


def monitor(api=github, detail_api=manus_detail):
    prs = read_open_prs() if api is github else read_open_prs_with(api)
    checked = updated = 0
    for pr in prs:
        number = pr.get("number")
        if type(number) is not int:
            continue
        comments = read_comments(number) if api is github else read_comments_with(api, number)
        for comment in comments:
            task = extract_task(comment, number)
            if task is None:
                continue
            try:
                result = detail_api(task["task_id"])
                current = api(f"/pulls/{number}")
                current_sha = (current.get("head") or {}).get("sha")
                if not isinstance(current_sha, str) or not SHA.fullmatch(current_sha):
                    raise ValueError("Cannot independently verify current PR HEAD")
                status = outcome_status(result, current_sha, task["sha"])
                checked += 1
                if status in ACTIVE or status == "UNKNOWN":
                    continue
                api(f"/issues/comments/{task['comment_id']}", "PATCH", {
                    "body": note_for(task, number, status, current_sha)
                })
                updated += 1
                print(f"TERMINAL: PR={number} Manus task state={status}, manual code review needed")
            except Exception as exc:
                # Never print API payloads, credentials or PR body to logs.
                print(f"UNCERTAIN: PR={number} monitor error={type(exc).__name__}")
    print(f"Monitoring complete: checked={checked} updated={updated}")
    return checked, updated


def read_open_prs_with(api):
    prs = api(f"/pulls?state=open&per_page={MAX_OPEN_PRS}")
    if not isinstance(prs, list) or len(prs) >= MAX_OPEN_PRS:
        raise RuntimeError("Open PR listing incomplete")
    return [p for p in prs if (p.get("user") or {}).get("login") == "shimamu34"
            and (p.get("base") or {}).get("ref") == "main"]


def read_comments_with(api, number):
    results = []
    for page in range(1, MAX_COMMENT_PAGES + 1):
        items = api(f"/issues/{number}/comments?per_page=100&page={page}")
        if not isinstance(items, list):
            raise RuntimeError("PR comments listing incomplete")
        results.extend(items)
        if len(items) < 100:
            return results
    raise RuntimeError("Comment listing truncated")


if __name__ == "__main__":
    if os.environ.get("ENABLE_MANUS_IMPLEMENTATION") != "true":
        print("DISABLED: no Manus status polling; enable explicit opt-in first")
    else:
        monitor()
