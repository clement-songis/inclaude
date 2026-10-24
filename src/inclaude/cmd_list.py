"""List the desktop app's sessions, by account and workspace.

Ids are shortened to their first eight characters; every other command accepts
any unique prefix. Accounts are labelled with what is known locally: `current`
for the one the app last signed in with, and the email of the one the CLI is
signed in with.
"""
from . import options, store


def register(sub):
    parser = sub.add_parser("list", help="the app's sessions, per account",
                            description=__doc__)
    options.add_account(parser)
    options.add_filters(parser)
    parser.set_defaults(func=run)


def run(args):
    spaces = store.workspaces()
    labels = store.account_labels()
    if args.account:
        spaces = [store.resolve_workspace(args.account, spaces, labels)]
    for ws in spaces:
        records = [rec for _, rec in store.load_records(ws)]
        shown = [rec for rec in records if store.matches_filters(rec, args)]
        count = f"{len(records)} sessions"
        if len(shown) != len(records):
            count += f", {len(shown)} shown"
        print(f"{store.describe(ws, labels)}  --  {count}")
        shown.sort(key=lambda rec: rec.get("lastActivityAt") or 0, reverse=True)
        for rec in shown:
            print("  " + store.row(rec))
        print()
