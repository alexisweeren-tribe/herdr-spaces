#!/usr/bin/env python3
"""herdr-spaces — background daemon that names Herdr workspaces from agent context."""

import json
import os
import subprocess
import sys
from pathlib import Path

RUN_INTERVAL = 600  # launchd fires us every 10 minutes; we poll once and exit
MAX_LABEL_LEN = 45
MAX_WORDS = 4
STATE_FILE = Path.home() / ".config" / "herdr-spaces" / "state.json"

HERDR_SEARCH_PATHS = [
    "/opt/homebrew/bin/herdr",
    "/usr/local/bin/herdr",
    str(Path.home() / ".local/bin/herdr"),
    str(Path.home() / ".cargo/bin/herdr"),
]


def find_herdr():
    for p in HERDR_SEARCH_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return "herdr"


HERDR = find_herdr()


def run_herdr(*args):
    try:
        r = subprocess.run(
            [HERDR, *args], capture_output=True, timeout=10
        )
        return r.stdout if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_snapshot():
    data = run_herdr("api", "snapshot")
    if not data:
        return None
    try:
        return json.loads(data)["result"]["snapshot"]
    except (json.JSONDecodeError, KeyError):
        return None


def read_agent_terminal(pane_id):
    data = run_herdr("agent", "read", pane_id, "--source", "visible", "--format", "text")
    if not data:
        return None
    return data.decode("utf-8", errors="replace")


def git_context(cwd):
    """Get repo basename and branch from a directory."""
    if not cwd or cwd == os.path.expanduser("~"):
        return None, None
    try:
        toplevel = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        branch = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        repo = (
            os.path.basename(toplevel.stdout.strip())
            if toplevel.returncode == 0
            else None
        )
        br = branch.stdout.strip() if branch.returncode == 0 else None
        return repo, br
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None, None


def extract_cwd_from_terminal(text):
    """Try to find the working directory from Claude Code's prompt line."""
    if not text:
        return None
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("> ") and ("~" in stripped or "/" in stripped):
            continue
        parts = stripped.split()
        for part in parts:
            expanded = os.path.expanduser(part) if part.startswith("~") else part
            if expanded.startswith("/") and os.path.isdir(expanded):
                return expanded
    return None


def strip_spinner(title):
    """Strip leading spinner glyphs (◐◑◒◓✳ etc.) that Claude Code prepends."""
    i = 0
    for ch in title:
        if ch.isalpha() or ch.isdigit():
            break
        i += 1
    return title[i:].strip() if i > 0 else title.strip()



NOISE_WORDS = {
    "with", "the", "a", "an", "and", "for", "of", "to", "in", "on",
    "from", "by", "via", "using", "into",
}


def shorten(title):
    """Condense a title to at most MAX_WORDS meaningful words."""
    words = title.split()
    kept = [w for w in words if w.lower() not in NOISE_WORDS]
    if len(kept) <= MAX_WORDS:
        return " ".join(kept)
    return " ".join(kept[:MAX_WORDS])


def deduplicate_labels(labels):
    """Given {ws_id: (short_label, full_kept_words)}, resolve collisions
    by appending extra words from the full list until labels are unique."""
    short_to_ids = {}
    for ws_id, (short, full) in labels.items():
        short_to_ids.setdefault(short, []).append(ws_id)

    result = {}
    for short, ids in short_to_ids.items():
        if len(ids) == 1:
            result[ids[0]] = short
            continue
        for ws_id in ids:
            _, full = labels[ws_id]
            for n in range(MAX_WORDS + 1, len(full) + 1):
                candidate = " ".join(full[:n])
                taken = [result.get(other) for other in ids if other != ws_id]
                if candidate not in taken:
                    result[ws_id] = candidate
                    break
            else:
                result[ws_id] = " ".join(full)
    return result


def rename_workspace(workspace_id, label):
    run_herdr("workspace", "rename", workspace_id, label)


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"managed": {}}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def poll_once(state):
    snapshot = get_snapshot()
    if not snapshot:
        return state

    workspaces = {w["workspace_id"]: w for w in snapshot.get("workspaces", [])}
    agents_by_ws = {}
    for a in snapshot.get("agents", []):
        ws_id = a.get("workspace_id")
        if ws_id:
            agents_by_ws.setdefault(ws_id, []).append(a)

    managed = state.get("managed", {})

    # Phase 1: compute candidate labels for all eligible workspaces
    candidates = {}
    for ws_id, ws in workspaces.items():
        current_label = ws.get("label", "")
        agents = agents_by_ws.get(ws_id, [])
        if not agents:
            continue
        is_default = current_label in ("~", "")
        is_managed = ws_id in managed
        if not is_default and not is_managed:
            continue

        agent = agents[0]
        raw_title = agent.get("terminal_title_stripped", "").strip()
        title = strip_spinner(raw_title)
        cwd = agent.get("foreground_cwd") or agent.get("cwd", "")
        status = agent.get("agent_status", "unknown")
        repo, branch = git_context(cwd)

        if title:
            words = title.split()
            kept = [w for w in words if w.lower() not in NOISE_WORDS]
            short = " ".join(kept[:MAX_WORDS])
            candidates[ws_id] = (short, kept, status, repo, branch)
        elif repo:
            fallback = f"{repo}/{branch}" if branch and branch != "main" else repo
            candidates[ws_id] = (fallback, fallback.split(), status, repo, branch)
        elif cwd and cwd != os.path.expanduser("~"):
            fallback = os.path.basename(cwd) or "~"
            candidates[ws_id] = (fallback, fallback.split(), status, repo, branch)

    # Phase 2: resolve collisions
    if candidates:
        short_map = {ws_id: (short, kept) for ws_id, (short, kept, *_) in candidates.items()}
        resolved = deduplicate_labels(short_map)
    else:
        resolved = {}

    # Phase 3: apply prefixes and rename
    for ws_id, label in resolved.items():
        _, _, status, _, _ = candidates[ws_id]
        if status == "blocked":
            label = "! " + label
        if len(label) > MAX_LABEL_LEN:
            label = label[: MAX_LABEL_LEN - 1] + "…"

        current_label = workspaces[ws_id].get("label", "")
        if label != current_label:
            rename_workspace(ws_id, label)
            managed[ws_id] = label
            print(f"  {ws_id}: {current_label!r} -> {label!r}")

    managed = {k: v for k, v in managed.items() if k in workspaces}
    state["managed"] = managed
    save_state(state)
    return state


def main():
    poll_once(load_state())


if __name__ == "__main__":
    main()
