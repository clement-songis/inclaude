"""List the CLI's transcripts, newest first, and whether the app lists them.

`imported` means some workspace has a record pointing at the transcript;
`deleted` means one has a tombstone for it, that is, the session was removed
from the app's list.
"""
import os
import time

from . import options, store, transcripts


def register(sub):
    parser = options.subparser(sub, "transcripts",
                             "the CLI's transcripts and their status", __doc__)
    parser.add_argument("--limit", type=int, default=40, metavar="N",
                        help="show the N most recent (default 40, 0 for all)")
    parser.set_defaults(func=run)


def run(args):
    known, deleted = set(), set()
    for ws in store.workspaces():
        known |= {rec.get("cliSessionId") for _, rec in store.load_records(ws)}
        deleted |= set(store.tombstones(ws))
    rows = []
    for cli_id, path in transcripts.candidates().items():
        flag = "imported" if cli_id in known else "deleted" if cli_id in deleted else ""
        rows.append((os.path.getmtime(path), cli_id,
                     os.path.basename(os.path.dirname(path)), flag))
    rows.sort(reverse=True)
    if args.limit:
        rows = rows[:args.limit]
    for mtime, cli_id, project, flag in rows:
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
        print(f"{stamp}  {cli_id}  {project:<45} {flag}")
