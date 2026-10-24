"""Move sessions from one account's list to another's.

The desktop app files its session list by account. Sign in with a second
account -- work next to personal, say -- and the left pane starts out empty:
every session opened under the first one sits in that account's directory,
and the UI has nothing to carry it across. The transcripts are shared, so
moving a session is moving its record into the other directory, with some
bookkeeping around it:

  - `archived-sessions.idx`, where a workspace has one, is kept in step, so an
    archived session stays archived instead of surfacing on one side or
    vanishing on the other. A workspace without an index is left without one;
  - a `deleted_<cliSessionId>` tombstone at the destination is removed. It
    said the conversation was unwanted there, and moving it in says otherwise;
  - `bridgeSessionIds` is emptied, `steeredByRemoteClient` cleared and
    `indexedAt` dropped. All three describe server-side state of the account
    that created them, which the other account cannot pick up. The app
    recreates them on demand;
  - `remoteMcpServersConfig` is taken from the destination's most recent
    record, since it describes the connectors of the workspace the session now
    lives in. It is left alone when the destination has no record to copy from.

What a move cannot do: artifacts published from the session belong to the
account that published them, and the links kept in `publishedArtifacts` go on
pointing at it. Sidebar sections and pins are the app's own per-account state
(its local storage, not this store), so a moved session lands in the plain
list.

Sessions are named by any unique prefix of the id after `local_`, as
`inclaude list` prints them, or by their cliSessionId. With two workspaces in
the store, --to (and --from) can be left out: the other one is meant.
"""
import collections
import os

from . import options, store, ui


def register(sub):
    parser = options.subparser(sub, "move", "sessions from one account to another", __doc__)
    parser.add_argument("sessions", nargs="*", metavar="SESSION",
                        help="a session to move, by id prefix or cliSessionId")
    parser.add_argument("--all", action="store_true",
                        help="move every session of the --from workspace")
    parser.add_argument("--from", dest="src", metavar="ACCOUNT",
                        help="workspace to move out of")
    parser.add_argument("--to", dest="dst", metavar="ACCOUNT",
                        help="workspace to move into")
    options.add_filters(parser)
    options.add_write(parser)
    parser.set_defaults(func=run)


def find_session(spec, index):
    """One entry of `index`, a list of (workspace, path, record). The spec is
    a sessionId with or without its local_ prefix, any unique prefix of it,
    or a cliSessionId."""
    bare = spec[len("local_"):] if spec.startswith("local_") else spec
    exact = [e for e in index if e[2]["sessionId"] == f"local_{bare}"
             or e[2].get("cliSessionId") == bare]
    hits = exact or [e for e in index
                     if e[2]["sessionId"].startswith(f"local_{bare}")]
    if not hits:
        store.die(f"no session matches {spec!r}; `inclaude list` shows them")
    if len({e[2]["sessionId"] for e in hits}) < len(hits):
        # Never seen; a record copied by hand, or a move interrupted between
        # its write and its unlink. Not something to paper over.
        store.die(f"{hits[0][2]['sessionId']} exists in several workspaces -- "
                  "sort that out by hand")
    if len(hits) > 1:
        store.die(f"{spec!r} matches several sessions: "
                  + ", ".join(e[2]["sessionId"] for e in hits))
    return hits[0]


def rehome(rec, mcp_config):
    """The record as the destination account should see it."""
    rec = dict(rec)
    if "bridgeSessionIds" in rec:
        rec["bridgeSessionIds"] = []
    if "steeredByRemoteClient" in rec:
        rec["steeredByRemoteClient"] = False
    rec.pop("indexedAt", None)
    if mcp_config:
        rec["remoteMcpServersConfig"] = mcp_config
    return rec


def pick_sessions(src, labels, args):
    """Let the user choose sessions to move from the source workspace."""
    records = [rec for _, rec in store.load_records(src)
               if store.matches_filters(rec, args)]
    records.sort(key=lambda rec: rec.get("lastActivityAt") or 0, reverse=True)
    if not records:
        store.die("no session to move out of " + store.describe(src, labels))
    chosen = ui.choose(records, store.row, "move which? ", multiple=True,
                       header=f"in {store.describe(src, labels)} "
                              "(a number, a range like 1-4, several, or 'all'):")
    return [(src, os.path.join(src.path, f"{rec['sessionId']}.json"), rec)
            for rec in chosen]


def run(args):
    spaces = store.workspaces()
    labels = store.account_labels()
    src = store.resolve_workspace(args.src, spaces, labels) if args.src else None
    dst = store.resolve_workspace(args.dst, spaces, labels) if args.dst else None
    asking = not args.all and not args.sessions and ui.interactive(args)
    if not args.all and not args.sessions and not asking:
        store.die("give sessions to move, or --all (or run in a terminal to "
                  "pick them); `inclaude list` shows them")
    if args.all and args.sessions:
        store.die("give sessions to move, or --all, not both")

    if args.all or asking:
        if src is None:
            if dst is not None:
                src = store.other_workspace(dst, spaces, labels)
            elif len(spaces) == 2:
                src = None  # resolved once dst is known, below
            if src is None and asking:
                src = store.choose_workspace(spaces, labels, "move out of which? ")
            if src is None:
                store.die("--all needs --from (or --to, with two workspaces)")
        if asking:
            chosen = pick_sessions(src, labels, args)
        else:
            chosen = [(src, path, rec) for path, rec in store.load_records(src)
                      if store.matches_filters(rec, args)]
    else:
        index = [(ws, path, rec) for ws in spaces
                 for path, rec in store.load_records(ws)]
        chosen, seen = [], set()
        for spec in args.sessions:
            entry = find_session(spec, index)
            if entry[2]["sessionId"] not in seen:
                seen.add(entry[2]["sessionId"])
                chosen.append(entry)
        strays = [e for e in chosen if src and e[0] != src]
        if strays:
            store.die("not in --from " + store.describe(src, labels) + ": "
                      + ", ".join(e[2]["sessionId"] for e in strays))
    if not chosen:
        print("nothing to move")
        return
    if dst is None:
        sources = {e[0] for e in chosen}
        if len(sources) != 1:
            store.die("the sessions come from several workspaces, say where "
                      "they go with --to")
        source = sources.pop()
        if len(spaces) == 2:
            dst = store.other_workspace(source, spaces, labels)
        elif ui.interactive(args):
            dst = store.choose_workspace(spaces, labels, "move into which? ",
                                         exclude=source)
        if dst is None:
            store.die("say where they go with --to")

    dst_records = store.load_records(dst)
    dst_ids = {rec["sessionId"] for _, rec in dst_records}
    dst_twins = {rec["cliSessionId"]: rec["sessionId"]
                 for _, rec in dst_records if rec.get("cliSessionId")}
    moves, skipped = [], []
    for ws, path, rec in chosen:
        if ws == dst:
            skipped.append((rec, "already there"))
        elif rec["sessionId"] in dst_ids:
            store.die(f"{rec['sessionId']} exists on both sides -- sort that "
                      "out by hand")
        elif rec.get("cliSessionId") in dst_twins:
            skipped.append((rec, "conversation already listed there as "
                            + dst_twins[rec["cliSessionId"]]))
        else:
            moves.append((ws, path, rec))

    for rec, why in skipped:
        print(f"skipped  {store.row(rec)}\n         {why}")
    if skipped:
        print()
    if not moves:
        print("nothing to move")
        return
    by_source = collections.OrderedDict()
    for ws, path, rec in moves:
        by_source.setdefault(ws, []).append(rec)
    for ws, records in by_source.items():
        print(f"from {store.describe(ws, labels)} to {store.describe(dst, labels)}: "
              f"{len(records)} session{'s' if len(records) > 1 else ''}")
        for rec in records:
            print("  " + store.row(rec))
        print()

    if args.dry_run:
        print("--dry-run: nothing written")
        return
    store.prepare_write(args)

    mcp_config = store.newest_mcp_config(dst)
    indexes = {ws: store.archive_index(ws) for ws in list(by_source) + [dst]}
    for ws, path, rec in moves:
        store.write_record(dst, rehome(rec, mcp_config))
        os.remove(path)
        if indexes[ws] and rec["sessionId"] in indexes[ws]["archived"]:
            indexes[ws]["archived"].remove(rec["sessionId"])
        if indexes[dst] and rec.get("isArchived") \
                and rec["sessionId"] not in indexes[dst]["archived"]:
            indexes[dst]["archived"].append(rec["sessionId"])
        tombstone = os.path.join(dst.path, f"deleted_{rec.get('cliSessionId')}")
        if rec.get("cliSessionId") and os.path.exists(tombstone):
            os.remove(tombstone)
            print(f"dropped the tombstone {os.path.basename(tombstone)}")
    for ws, data in indexes.items():
        if data:
            store.write_archive_index(ws, data)
    print(f"moved: {len(moves)} session{'s' if len(moves) > 1 else ''} "
          f"into {dst.path}")
