"""Flags shared by several commands."""
import argparse


def subparser(sub, name, help, description):
    """A subcommand whose long description keeps the line breaks it was
    written with."""
    return sub.add_parser(name, help=help, description=description,
                          formatter_class=argparse.RawDescriptionHelpFormatter)


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
    parser.add_argument("--kill", action="store_true",
                        help="quit claude-desktop first, without asking")
    parser.add_argument("--force", action="store_true",
                        help="write even though claude-desktop is running, "
                             "underneath it (last resort)")
    parser.add_argument("--no-input", action="store_true",
                        help="never stop to ask; error instead of prompting")
