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

Run `import` or `move` with no id, from a terminal, and they show a numbered
menu to pick from instead of making you hunt for one; the same goes for the
account when it is ambiguous. Pass the ids (and `--account`/`--from`/`--to`)
to skip the menus, or `--no-input` to forbid them so a script errors rather
than blocks.

## Install / run

With Homebrew (macOS), the formula lives in this repository:

```
brew tap clement-songis/inclaude https://github.com/clement-songis/inclaude
brew install inclaude
```

With Nix flakes:

```
nix run github:clement-songis/inclaude -- list
```

or add the flake as an input and install `packages.${system}.default`, or
apply `overlays.default` and install `pkgs.inclaude`. Without Nix, it is a
plain Python package with no dependencies: `pip install .` (Python 3.10+).

Linux and macOS. The store lives under `~/.config/Claude` on Linux and under
`~/Library/Application Support/Claude` on macOS; paths below use the Linux
one. On macOS the app is quit through AppleScript, like Cmd+Q.

## Before writing anything

**The desktop app has to quit first.** It holds its list in memory and writes
it back out on exit, which would undo whatever was done underneath it. So every
writing command, when the app is up, either quits it or stops:

- from a terminal it offers to quit the app, waits for it, then proceeds;
- `--kill` quits it outright, no question asked;
- `--force` writes underneath the running app anyway, a last resort that the
  app may overwrite when it exits;
- otherwise it stops and tells you to quit the app (this is what `--no-input`
  gets in a script).

Each writing command also shows its plan first (`--dry-run` stops there) and
copies the whole store to `~/.config/Claude/claude-code-sessions.bak-<timestamp>`
before touching it (`--no-backup` skips that).

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
