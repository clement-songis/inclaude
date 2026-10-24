"""Import every terminal session the desktop app does not already list.

The bulk counterpart of `import`; everything here is about deciding *which*
transcripts deserve a record, which is the only hard part of doing it in bulk.

One conversation, one record. Resuming a session does not append to its
transcript: it writes a *new* .jsonl whose messages repeat the whole history
under their original uuids, so a conversation picked up twenty times leaves
twenty files that are all the same conversation at different lengths. Message
uuids are stable across those resumes, so the first one names the conversation
and the rest say who contains whom. A transcript is dropped when another one
of its group holds all but a handful of its messages; that handful is the
trailing exchange a resume leaves behind.

The threshold is not cosmetic. Resuming is also how a conversation is
*forked*, and a fork keeps content the longest transcript never had -- so
"keep the longest of each group" quietly throws work away. Measured on one
store, the gap between leftovers and real branches ran from a couple of dozen
messages straight to several hundred; --branch-threshold sits in that gap,
and anything above it is listed on its own. --all-resumes turns the whole
thing off, one record per transcript.

Being already known is a fact about the conversation, not about the file: a
transcript already contained in one the app lists (or has a tombstone for) is
skipped, so the older copies of a listed conversation stay out while a genuine
fork of it still comes in.

What else gets skipped, and why:

  - transcripts the app has a `deleted_<id>` tombstone for, unless they have
    grown since. Importing blind would resurrect conversations that were
    deliberately thrown away, but the marker only speaks for the conversation
    as it stood then: one resumed after its deletion comes back.
    --include-deleted ignores the markers entirely;
  - transcripts with no `assistant` record. A session that was opened and
    abandoned still leaves a few lines of prompts and metadata, and there is
    nothing in it to resume;
  - anything below --min-turns, outside --project, or older than --since.

Size warning: `remoteMcpServersConfig` is mandatory in a record and is a full
dump of every MCP tool schema, often a few hundred KB. It dominates the
record, so importing 80 sessions can add some 20 MB to the store.
"""
import os
import time

from . import cmd_import, options, store, transcripts


def register(sub):
    parser = sub.add_parser("sync", help="every missing terminal session into the app",
                            description=__doc__)
    options.add_account(parser)
    options.add_filters(parser)
    parser.add_argument("--min-turns", type=int, default=1,
                        help="skip sessions with fewer user turns (default 1)")
    parser.add_argument("--limit", type=int, help="import at most N sessions")
    parser.add_argument("--include-deleted", action="store_true",
                        help="also import sessions deleted from the app's list")
    parser.add_argument("--all-resumes", action="store_true",
                        help="one record per transcript instead of one per "
                             "conversation")
    parser.add_argument("--branch-threshold", type=int, default=32, metavar="N",
                        help="a transcript keeping more than N messages its "
                             "longer sibling lacks is a branch, and is listed "
                             "on its own (default 32)")
    options.add_write(parser)
    parser.set_defaults(func=run)


def held_by(me, uuids, others, threshold):
    """The longest entry of `others` holding all but `threshold` of `uuids`.

    `others` is a list of (key, uuids). A transcript that lost more than the
    threshold to a sibling diverged from it -- that is a branch, and it is
    listed on its own rather than folded into the longer one. Rank ties break
    on the key so that two transcripts can never hold each other.
    """
    mine, best = set(uuids), None
    for key, theirs in others:
        if key == me or (len(theirs), str(key)) <= (len(uuids), str(me)):
            continue
        if len(mine - set(theirs)) <= threshold:
            if best is None or len(theirs) > best[1]:
                best = (key, len(theirs))
    return best


def run(args):
    spaces = store.workspaces()
    labels = store.account_labels()
    ws = store.pick_workspace(args.account, spaces, labels)
    known = {rec.get("cliSessionId") for _, rec in store.load_records(ws)}
    deleted = {} if args.include_deleted else store.tombstones(ws)
    cutoff = time.time() - args.since * 86400 if args.since else None
    candidates = transcripts.candidates()

    # Conversations the app has already made up its mind about, kept or thrown
    # away, indexed by lineage so a candidate can be tested against them.
    settled = {}
    if not args.all_resumes:
        for cli_id in known | set(deleted):
            path = candidates.get(cli_id)
            uuids = transcripts.lineage_of(path) if path else None
            if uuids:
                settled.setdefault(uuids[0], []).append((cli_id, uuids))

    todo, skipped = [], {}

    def skip(reason, count=1):
        skipped[reason] = skipped.get(reason, 0) + count

    for cli_id, path in candidates.items():
        if cli_id in known:
            skip("already in the app")
            continue
        if cutoff and os.path.getmtime(path) < cutoff:
            skip(f"older than {args.since:g} days")
            continue
        meta = transcripts.scan_transcript(path)
        if not meta["replies"]:
            skip("no assistant reply")
            continue
        if meta["turns"] < args.min_turns:
            skip(f"fewer than {args.min_turns} turns")
            continue
        if args.project and args.project not in (" ".join(meta["cwds"]) or path):
            skip(f"not under {args.project!r}")
            continue
        if cli_id in deleted:
            # Deleted, and nothing has happened in it since -- the deletion
            # still describes the conversation as it stands.
            _, last = transcripts.time_bounds(meta, path)
            if last <= deleted[cli_id]:
                skip("deleted from the app")
                continue
        if held_by(cli_id, meta["uuids"], settled.get(meta["root"], []),
                   args.branch_threshold):
            skip("already held by a session in the app")
            continue
        todo.append((cli_id, path, meta))

    folded = {}
    if not args.all_resumes:
        # Fold each transcript into the longest sibling that holds it, so a
        # conversation resumed twenty times is listed once -- but a fork, which
        # keeps what that sibling never had, stays on its own.
        groups = {}
        for item in todo:
            groups.setdefault(item[2]["root"] or item[0], []).append(item)
        kept = []
        for members in groups.values():
            others = [(m[0], m[2]["uuids"]) for m in members]
            for item in members:
                holder = held_by(item[0], item[2]["uuids"], others,
                                 args.branch_threshold)
                if holder:
                    folded[holder[0]] = folded.get(holder[0], 0) + 1
                else:
                    kept.append(item)
        if len(todo) != len(kept):
            skip("held by another transcript below", len(todo) - len(kept))
        todo = kept

    todo.sort(key=lambda item: item[2]["last_ts"] or "")
    if args.limit:
        dropped = len(todo) - args.limit
        if dropped > 0:
            todo = todo[-args.limit:]
            skipped[f"beyond --limit {args.limit}"] = dropped

    for reason, count in sorted(skipped.items()):
        print(f"skipped {count:>3}  {reason}")
    if not todo:
        print("\nnothing to import")
        return

    mcp_config = store.newest_mcp_config(ws) if not args.dry_run else []
    records = []
    print(f"\nto import into {store.describe(ws, labels)}: {len(todo)}\n")
    for cli_id, path, meta in todo:
        record = cmd_import.build_record(cli_id, meta, path, mcp_config)
        records.append(record)
        stamp = time.strftime("%Y-%m-%d %H:%M",
                              time.localtime(record["lastActivityAt"] / 1000))
        where = record["cwd"].replace(store.HOME + "/", "~/")
        # Elide from the left: worktree paths only differ at their tail.
        if len(where) > 38:
            where = "…" + where[-37:]
        count = folded.get(cli_id, 0)
        title = record["title"][:40] + (f"  (+{count} resumes)" if count else "")
        print(f"{stamp}  {meta['turns']:>4} turns  {where:<38} {title}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return
    print()
    store.prepare_write(args)
    for record in records:
        store.write_record(ws, record)
    print(f"wrote: {len(records)} records into {ws.path}")
