"""Command line entry point: one binary, one subcommand per job."""
import argparse

from . import __version__, cmd_import, cmd_list, cmd_move, cmd_sync, cmd_transcripts

DESCRIPTION = """\
inclaude -- include your terminal Claude Code sessions in the desktop app's
list, and move them between accounts.

The desktop app keeps its own per-account list of sessions and has no import;
the CLI keeps transcripts it never shows. These commands bridge the two by
writing the app's metadata records directly. The app has to quit before any
command that writes, since it keeps the list in memory and writes it back out
on exit: from a terminal inclaude offers to quit it, --kill does so outright.
The whole store is copied to a timestamped .bak before every write.

Run import or move with no id, from a terminal, to pick from a menu instead
of looking one up; pass ids and --account to skip the menus, --no-input to
forbid them.

Commands:
  list          the app's sessions, per account
  transcripts   the CLI's transcripts and whether the app lists them
  import        one terminal session into the app
  sync          every terminal session the app is missing
  move          sessions from one account to another
"""


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="inclaude", description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"inclaude {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    for module in (cmd_list, cmd_transcripts, cmd_import, cmd_sync, cmd_move):
        module.register(sub)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    main()
