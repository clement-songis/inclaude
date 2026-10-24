"""The desktop app's session store, as read off a live installation.

The app lists one metadata record per session under

  ~/.config/Claude/claude-code-sessions/<account>/<workspace>/local_<uuid>.json

where <account> and <workspace> are the uuids of the signed-in account and of
its organisation. A record holds metadata only -- title, cwd, model, archive
flag, and so on -- and points by `cliSessionId` at the transcript the CLI
keeps in ~/.claude/projects, which every account shares. Next to the records:

  - `archived-sessions.idx`, when present, lists exactly the records flagged
    `isArchived`;
  - `deleted_<cliSessionId>` is a 13-byte tombstone holding the time a session
    was removed from the list;
  - `scheduled-tasks.json`, which is left alone.

None of this is documented or promised, and an app update can change it. Every
writer here copies the whole store to a timestamped `.bak` first, and refuses
to run while the app is up: it keeps the list in memory and writes it back out
on exit, undoing whatever was done underneath it.
"""
import collections
import glob
import json
import os
import re
import shutil
import sys
import time

HOME = os.path.expanduser("~")
APP_DIR = os.path.join(HOME, ".config", "Claude")
STORE_ROOT = os.path.join(APP_DIR, "claude-code-sessions")
APP_CONFIG = os.path.join(APP_DIR, "config.json")
CLI_CONFIG = os.path.join(HOME, ".claude.json")
ARCHIVE_INDEX = "archived-sessions.idx"

UUID = re.compile(r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")

Workspace = collections.namedtuple("Workspace", "account space path")

# Keys present in every record ever observed. Leaving one out risks tripping
# the app, so an imported record always carries them, with the majority value
# as default; everything else is optional and only added when the transcript
# actually supplies it.
REQUIRED_DEFAULTS = {
    "alwaysAllowedReasons": [],
    "chromePermissionMode": "skip_all_permission_checks",
    "classifierSummaryEnabled": True,
    "isArchived": False,
    "permissionMode": "bypassPermissions",
    "reportFindingsCard": True,
    "sessionPermissionUpdates": [],
    "spawnSeed": {},
}


def die(msg):
    sys.exit(f"error: {msg}")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_json(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def workspaces():
    """Every <account>/<workspace> of the store, by uuid-named directories
    only: `.bak-` copies left by earlier tools next to them are not
    workspaces."""
    found = []
    accounts = sorted(os.listdir(STORE_ROOT)) if os.path.isdir(STORE_ROOT) else []
    for account in accounts:
        if not UUID.match(account):
            continue
        for space in sorted(os.listdir(os.path.join(STORE_ROOT, account))):
            path = os.path.join(STORE_ROOT, account, space)
            if UUID.match(space) and os.path.isdir(path):
                found.append(Workspace(account, space, path))
    if not found:
        die(f"no desktop store under {STORE_ROOT} -- run the app once")
    return found


def account_labels():
    """What is known locally about each account uuid: which one the app last
    signed in with, and the email of the one the CLI is signed in with --
    ~/.claude.json is the only file around that pairs a uuid with an email."""
    labels = {}
    app = read_json(APP_CONFIG) or {}
    if app.get("lastKnownAccountUuid"):
        labels.setdefault(app["lastKnownAccountUuid"], []).append("current")
    cli = (read_json(CLI_CONFIG) or {}).get("oauthAccount") or {}
    if cli.get("accountUuid") and cli.get("emailAddress"):
        labels.setdefault(cli["accountUuid"], []).append(cli["emailAddress"])
    return labels


def describe(ws, labels):
    tags = labels.get(ws.account, [])
    short = f"{ws.account[:8]}/{ws.space[:8]}"
    return short + (f" ({', '.join(tags)})" if tags else "")


def resolve_workspace(spec, spaces, labels):
    """The workspace a user means: any unique prefix of the account uuid,
    optionally `/` and a prefix of the workspace uuid, or `current` for the
    account the app last signed in with."""
    if spec == "current":
        wanted = [a for a, tags in labels.items() if "current" in tags]
        matches = [w for w in spaces if w.account in wanted]
    else:
        account, _, space = spec.partition("/")
        matches = [w for w in spaces
                   if w.account.startswith(account) and w.space.startswith(space)]
    if not matches:
        die(f"no workspace matches {spec!r}; `inclaude list` shows them")
    if len(matches) > 1:
        die(f"{spec!r} is ambiguous: "
            + ", ".join(describe(w, labels) for w in matches))
    return matches[0]


def other_workspace(ws, spaces, labels):
    """The workspace meant when there are two and one is given."""
    others = [w for w in spaces if w != ws]
    if len(others) != 1:
        die("several workspaces to choose from, name one with --to/--from: "
            + ", ".join(describe(w, labels) for w in others))
    return others[0]


def pick_workspace(spec, spaces, labels):
    """The workspace a single-store command works in: the one asked for, else
    the only one, else the one of the account the app last signed in with."""
    if spec:
        return resolve_workspace(spec, spaces, labels)
    if len(spaces) == 1:
        return spaces[0]
    current = [w for w in spaces if "current" in labels.get(w.account, [])]
    if len(current) == 1:
        return current[0]
    die("several workspaces, pick one with --account: "
        + ", ".join(describe(w, labels) for w in spaces))


def load_records(ws):
    """(path, record) for every readable local_*.json of the workspace."""
    out = []
    for path in sorted(glob.glob(os.path.join(ws.path, "local_*.json"))):
        rec = read_json(path)
        if isinstance(rec, dict) and rec.get("sessionId"):
            out.append((path, rec))
    return out


def tombstones(ws):
    """When each `deleted_<id>` marker was written, by cliSessionId.

    The marker holds the deletion time in milliseconds, and that is the point:
    it says the conversation was unwanted *as it stood then*. Work done in it
    afterwards is not covered by that, so the timestamp comes back with the id
    rather than being thrown away. An unreadable marker counts as forever.
    """
    out = {}
    for path in glob.glob(os.path.join(ws.path, "deleted_*")):
        try:
            with open(path, encoding="utf-8") as fh:
                stamp = int(fh.read().strip())
        except (ValueError, OSError):
            stamp = float("inf")
        out[os.path.basename(path)[len("deleted_"):]] = stamp
    return out


def archive_index(ws):
    """The archived-sessions.idx of a workspace, or None when it has none."""
    path = os.path.join(ws.path, ARCHIVE_INDEX)
    if not os.path.exists(path):
        return None
    data = read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("archived"), list):
        die(f"unreadable {path}")
    return data


def write_archive_index(ws, data):
    write_json(os.path.join(ws.path, ARCHIVE_INDEX), data)


def newest_mcp_config(ws):
    """`remoteMcpServersConfig` of the most recently written record. It is
    mandatory, never empty in any observed record, and describes the
    connectors of this workspace, so it is copied rather than invented."""
    best, best_mtime = None, -1.0
    for path, rec in load_records(ws):
        mtime = os.path.getmtime(path)
        if rec.get("remoteMcpServersConfig") and mtime > best_mtime:
            best, best_mtime = rec["remoteMcpServersConfig"], mtime
    return best or []


def write_record(ws, record):
    path = os.path.join(ws.path, f"{record['sessionId']}.json")
    write_json(path, record)
    return path


def backup_store():
    """Copy the whole store next to itself, every account, minus the .bak-
    copies earlier tools left inside it."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = f"{STORE_ROOT}.bak-{stamp}"
    shutil.copytree(STORE_ROOT, target, ignore=shutil.ignore_patterns("*.bak-*"))
    return target


def app_running():
    """True if a claude-desktop process is alive. Reads /proc directly so the
    package needs no runtime dependency just to call pgrep."""
    for entry in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(entry, "rb") as fh:
                if b"claude-desktop" in fh.read():
                    return True
        except OSError:
            continue
    return False


def prepare_write(args):
    """The checks every writer runs after showing its plan: the app must be
    down (or --force given), and the store is backed up (unless --no-backup)."""
    if app_running() and not args.force:
        die("claude-desktop is running. It keeps this list in memory and writes "
            "it back out on exit, which would undo this. Quit it and re-run "
            "(or pass --force).")
    if not args.no_backup:
        print(f"backup: {backup_store()}")


def row(rec):
    """One line of a session listing."""
    stamp = time.strftime("%Y-%m-%d %H:%M",
                          time.localtime((rec.get("lastActivityAt") or 0) / 1000))
    where = (rec.get("cwd") or "").replace(HOME + "/", "~/")
    # Elide from the left: worktree paths only differ at their tail.
    if len(where) > 30:
        where = "…" + where[-29:]
    flag = "archived" if rec.get("isArchived") else ""
    short = rec["sessionId"][len("local_"):][:8]
    return f"{stamp}  {short}  {flag:<8}  {where:<30} {(rec.get('title') or '')[:48]}"


def matches_filters(rec, args):
    if args.project and args.project not in (rec.get("cwd") or ""):
        return False
    if args.since:
        cutoff = (time.time() - args.since * 86400) * 1000
        if (rec.get("lastActivityAt") or 0) < cutoff:
            return False
    return True
