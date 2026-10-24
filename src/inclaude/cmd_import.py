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

from . import options, store, transcripts, ui


def register(sub):
    parser = options.subparser(sub, "import", "one terminal session into the app", __doc__)
    parser.add_argument("cli_session_id", metavar="CLI_SESSION_ID", nargs="?",
                        help="the transcript's name under ~/.claude/projects; "
                             "omit to pick one from a menu")
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


def pick_transcript(ws, args):
    """Let the user choose a transcript the workspace does not already list.
    Returns (cli_id, path, meta)."""
    known = {rec.get("cliSessionId") for _, rec in store.load_records(ws)}
    rows = []
    for cli_id, path in transcripts.candidates().items():
        if cli_id in known:
            continue
        meta = transcripts.scan_transcript(path)
        if not meta["replies"]:
            continue
        _, last = transcripts.time_bounds(meta, path)
        rows.append((last, cli_id, path, meta))
    rows.sort(reverse=True)
    if not rows:
        store.die("no terminal session left to import into "
                  + store.describe(ws, store.account_labels()))

    def render(r):
        last, cli_id, path, meta = r
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(last / 1000))
        where = (meta["cwds"][-1] if meta["cwds"] else "").replace(
            store.HOME + "/", "~/")
        if len(where) > 34:
            where = "…" + where[-33:]
        title = meta["custom_title"] or meta["ai_title"] or ""
        return f"{stamp}  {meta['turns']:>4} turns  {where:<34} {title[:40]}"

    chosen = ui.choose(rows, render, "import which? ",
                       header=f"importable into {store.describe(ws, store.account_labels())}:")
    if not chosen:
        store.die("nothing picked")
    return chosen[1], chosen[2], chosen[3]


def run(args):
    spaces = store.workspaces()
    labels = store.account_labels()
    ws = store.pick_workspace(args.account, spaces, labels, args)

    if args.cli_session_id:
        path = transcripts.find_transcript(args.cli_session_id)
        meta = transcripts.scan_transcript(path)
        cli_id = args.cli_session_id
    elif ui.interactive(args):
        cli_id, path, meta = pick_transcript(ws, args)
    else:
        store.die("give a cliSessionId (or run in a terminal to pick one)")

    existing = next((rec for _, rec in store.load_records(ws)
                     if rec.get("cliSessionId") == cli_id), None)
    mcp_config = store.newest_mcp_config(ws) if not existing else None
    record = build_record(cli_id, meta, path, mcp_config,
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
