"""The CLI's side: transcripts under ~/.claude/projects.

A session started with `claude` in a terminal is appended to
~/.claude/projects/<cwd with "/" and "." turned into "-">/<cliSessionId>.jsonl,
one JSON record per line. Everything a desktop record needs -- title, cwd,
branch, model, time bounds, turn count -- can be read back out of it.
"""
import datetime
import glob
import json
import os

from .store import HOME, die

PROJECTS = os.path.join(HOME, ".claude", "projects")


def project_dir_name(cwd):
    """How ~/.claude/projects names the directory for a cwd: "/" and "." to "-"."""
    return cwd.replace("/", "-").replace(".", "-")


def find_transcript(cli_id):
    hits = glob.glob(os.path.join(PROJECTS, "*", f"{cli_id}.jsonl"))
    if not hits:
        die(f"no transcript for {cli_id} under {PROJECTS}")
    return hits[0]


def candidates():
    """One transcript per cliSessionId, the longest when a session moved
    (`relocated`, worktrees) and left copies under two project directories."""
    best = {}
    for path in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        cli_id = os.path.basename(path)[:-len(".jsonl")]
        kept = best.get(cli_id)
        if kept is None or os.path.getsize(path) > os.path.getsize(kept):
            best[cli_id] = path
    return best


def resolve_cwd(path, cwds):
    """The cwd this transcript belongs to: the one its directory encodes.

    An entry records the cwd it ran under, and that changes with every `cd`,
    but the transcript stays in the directory of the cwd the session opened in.
    Taking the last one hands the app a path it cannot map back to this file --
    a session that cd'd into a subdirectory then goes missing from the list --
    and taking the first is just as wrong for one that entered a worktree. The
    directory itself is the only reliable answer; the rest are files moved
    after the fact.
    """
    wanted = os.path.basename(os.path.dirname(path))
    for cwd in cwds:
        if project_dir_name(cwd) == wanted:
            return cwd
    return cwds[0] if cwds else None


def scan_transcript(path):
    """Everything a record needs, in one pass over the .jsonl.

    Every cwd the transcript mentions is kept, in order: the first is where the
    session started, and resolve_cwd() picks the one the app can map back to
    this file. They are read from the transcript rather than decoded from the
    directory name, which is lossy -- "/" and "." both become "-".
    """
    out = {"lines": 0, "turns": 0, "replies": 0, "uuids": [], "root": None,
           "ai_title": None, "custom_title": None, "cwds": [],
           "branch": None, "model": None, "effort": None,
           "first_ts": None, "last_ts": None}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            out["lines"] += 1
            kind = rec.get("type")
            if kind in ("user", "assistant") and rec.get("uuid"):
                out["uuids"].append(rec["uuid"])
                out["root"] = out["root"] or rec["uuid"]
            if kind == "user":
                out["turns"] += 1
            elif kind == "assistant":
                out["replies"] += 1
                # Both live on the record itself, and only the later turns of a
                # session carry them -- keep overwriting to end on the last.
                model = rec.get("message", {}).get("model")
                if model:
                    out["model"] = model
                if rec.get("effort"):
                    out["effort"] = rec["effort"]
            elif kind == "ai-title":
                out["ai_title"] = rec.get("aiTitle") or out["ai_title"]
            elif kind == "custom-title":
                out["custom_title"] = rec.get("customTitle") or out["custom_title"]
            if rec.get("cwd") and rec["cwd"] not in out["cwds"]:
                out["cwds"].append(rec["cwd"])
            if rec.get("gitBranch") and not out["branch"]:
                out["branch"] = rec["gitBranch"]
            stamp = rec.get("timestamp")
            if stamp:
                out["first_ts"] = out["first_ts"] or stamp
                out["last_ts"] = stamp
    return out


def lineage_of(path):
    """The message uuids of a transcript. The first one names the conversation."""
    uuids = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("type") in ("user", "assistant") and rec.get("uuid"):
                    uuids.append(rec["uuid"])
    except OSError:
        pass
    return uuids


def iso_to_ms(stamp, fallback):
    if not stamp:
        return fallback
    try:
        parsed = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ")
        return int(parsed.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    except ValueError:
        return fallback


def time_bounds(meta, path):
    fallback_ms = int(os.path.getmtime(path) * 1000)
    return iso_to_ms(meta["first_ts"], fallback_ms), iso_to_ms(meta["last_ts"], fallback_ms)
