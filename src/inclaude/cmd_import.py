"""Put one terminal session into the desktop app's list.

The CLI and the desktop app keep two separate lists. A session started with
`claude` in a terminal never appears in the app's left pane, which only lists
what it started itself, and there is no import in the UI: a long terminal
session is reachable only through `claude --resume`.

The gap is narrow. The app's records hold metadata only and point at the
transcript by `cliSessionId`, so importing is not a data migration: it is
writing the record that points at a transcript already sitting on disk. Only
the keys present in every observed record are written, with defaults taken
from the majority value; `remoteMcpServersConfig` is copied from the most
recent record of the workspace rather than invented. Re-importing an
already-imported session updates its record in place.
"""
import os
import time
import uuid

from . import options, store, transcripts


def register(sub):
    parser = sub.add_parser("import", help="one terminal session into the app",
                            description=__doc__)
    parser.add_argument("cli_session_id", metavar="CLI_SESSION_ID",
                        help="the transcript's name under ~/.claude/projects")
    parser.add_argument("--title", help="override the transcript's own title")
    parser.add_argument("--model", help="override the model read from the transcript")
    parser.add_argument("--effort", help="override the effort read from the transcript")
    options.add_account(parser)
    options.add_write(parser)
    parser.set_defaults(func=run)


def build_record(cli_id, meta, path, mcp_config, title=None, model=None,
                 effort=None, existing=None):
    """A record for the transcript, fresh or updating `existing`."""
    created, last = transcripts.time_bounds(meta, path)
    cwd = transcripts.resolve_cwd(path, meta["cwds"]) or os.path.dirname(path)
    record = dict(existing) if existing else {
        "sessionId": f"local_{uuid.uuid4()}",
        "remoteMcpServersConfig": mcp_config,
    }
    for key, value in store.REQUIRED_DEFAULTS.items():
        record.setdefault(key, value)
    record.update({
        "cliSessionId": cli_id,
        "cwd": cwd,
        "originCwd": meta["cwds"][0] if meta["cwds"] else cwd,
        "createdAt": created,
        "lastActivityAt": last,
        "lastFocusedAt": last,
        "model": model or meta["model"] or "claude-opus-5",
        "effort": effort or meta["effort"] or "high",
        "title": title or meta["custom_title"] or meta["ai_title"]
        or os.path.basename(cwd),
        "titleSource": "user" if (title or meta["custom_title"]) else "auto",
        "completedTurns": meta["turns"],
    })
    record.setdefault("bridgeSessionIds", [])
    if meta["branch"] and meta["branch"] != "HEAD":
        record.setdefault("branch", meta["branch"])
    return record


def run(args):
    spaces = store.workspaces()
    labels = store.account_labels()
    ws = store.pick_workspace(args.account, spaces, labels)
    path = transcripts.find_transcript(args.cli_session_id)
    meta = transcripts.scan_transcript(path)

    existing = next((rec for _, rec in store.load_records(ws)
                     if rec.get("cliSessionId") == args.cli_session_id), None)
    mcp_config = store.newest_mcp_config(ws) if not existing else None
    record = build_record(args.cli_session_id, meta, path, mcp_config,
                          args.title, args.model, args.effort, existing)

    fmt = "%Y-%m-%d %H:%M"
    print(f"{'update' if existing else 'create'}: {record['sessionId']} "
          f"in {store.describe(ws, labels)}")
    print(f"  title : {record['title']}")
    print(f"  cwd   : {record['cwd']}")
    print(f"  turns : {meta['turns']}")
    print(f"  from  : {time.strftime(fmt, time.localtime(record['createdAt'] / 1000))}")
    print(f"  to    : {time.strftime(fmt, time.localtime(record['lastActivityAt'] / 1000))}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return
    print()
    store.prepare_write(args)
    print(f"wrote: {store.write_record(ws, record)}")
