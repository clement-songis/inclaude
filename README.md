# inclaude

*include + Claude.* Include your terminal Claude Code sessions in the desktop
app's list, and move sessions between accounts.

The Claude desktop app (its Code tab) and the `claude` CLI keep two separate
lists of sessions. A session started in a terminal never shows up in the app's
left pane, and the app has no import. Sign in to the app with a second account
and the pane starts out empty: sessions are filed per account, and nothing
carries them across. `inclaude` fixes both by writing the app's own metadata
records.

```
inclaude list                        # the app's sessions, per account
inclaude transcripts                 # the CLI's transcripts, and which the app lists
inclaude import <cliSessionId>       # one terminal session into the app
inclaude sync --dry-run              # every terminal session the app is missing
inclaude move 9419e79b 3dc35ee9      # sessions from one account to the other
inclaude move --all --from c483 --to current --project nixos
```

## Install / run

With Nix flakes:

```
nix run github:clement-songis/inclaude -- list
```

or add the flake as an input and install `packages.${system}.default`, or
apply `overlays.default` and install `pkgs.inclaude`. Without Nix, it is a
plain Python package with no dependencies: `pip install .` (Python 3.10+).

Linux only: the store lives under `~/.config/Claude`. macOS keeps it under
`~/Library/Application Support` and has not been looked at.

## Before writing anything

**Quit the desktop app first.** It holds its list in memory and writes it back
out on exit, undoing whatever was done underneath it. Every writing command
refuses to run while the app is up (`--force` overrides), shows its plan first
(`--dry-run` stops there), and copies the whole store to
`~/.config/Claude/claude-code-sessions.bak-<timestamp>` before touching it
(`--no-backup` skips that).

## How it works

Everything below was read off a live store (claude-desktop 2.26454.0). None of
it is documented or promised by Anthropic, and an app update can change it
without warning. Hence the backups.

The app stores its list as one JSON file per session:

```
~/.config/Claude/claude-code-sessions/<account uuid>/<organisation uuid>/local_<uuid>.json
```

A record holds **metadata only** (title, cwd, model, archive flag, permission
mode, MCP connector snapshot, ...) and points at the transcript by one field,
`cliSessionId`. The transcript itself is the CLI's
`~/.claude/projects/<cwd with "/" and "." as "-">/<cliSessionId>.jsonl`, which
every account shares. So:

- **import** is writing one record that points at a transcript already on
  disk. Only the keys present in every observed record are written; the
  connector snapshot is copied from the newest existing record rather than
  invented.
- **sync** does that for every transcript the app is missing, and spends most
  of its effort deciding *which*: resuming a session writes a new transcript
  repeating the whole history, so one conversation is usually many files. They
  are folded together by message uuid, forks are kept apart, and sessions the
  app deleted (it leaves a `deleted_<cliSessionId>` tombstone) stay out unless
  they were worked in after the deletion. See `inclaude sync --help`.
- **move** carries a record into another account's directory, keeps
  `archived-sessions.idx` in step on both sides, drops a tombstone waiting at
  the destination, and resets the fields that name server-side state of the
  old account (`bridgeSessionIds`, `indexedAt`). Artifacts published from the
  session stay with the account that published them; sidebar sections and pins
  are the app's own state and are not moved. See `inclaude move --help`.

Accounts are named by any unique prefix of their uuid, as `inclaude list`
prints them, or by `current` for the one the app last signed in with. The
list labels an account with the CLI's signed-in email when `~/.claude.json`
pairs them.

## License

MIT.
