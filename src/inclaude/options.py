"""Flags shared by several commands."""


def add_account(parser):
    parser.add_argument("--account", metavar="ACCOUNT",
                        help="workspace to work in: a uuid prefix as `inclaude "
                             "list` prints them, or `current`. Defaults to the "
                             "only one, else to the app's current account")


def add_filters(parser):
    parser.add_argument("--project",
                        help="only sessions whose cwd contains this substring")
    parser.add_argument("--since", type=float, metavar="DAYS",
                        help="only sessions active in the last DAYS days")


def add_write(parser):
    parser.add_argument("--dry-run", action="store_true",
                        help="show the plan, write nothing")
    parser.add_argument("--no-backup", action="store_true",
                        help="skip the .bak copy of the store")
    parser.add_argument("--force", action="store_true",
                        help="write even though claude-desktop is running")
