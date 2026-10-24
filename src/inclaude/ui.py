"""Terminal interaction: confirmations, pickers, and quitting the app.

Everything here is a convenience for someone running inclaude by hand. None of
it fires when there is no terminal on stdin or when --no-input is passed: a
command run from a script then behaves exactly as it did with arguments only,
erroring instead of stopping to ask.
"""
import glob
import os
import signal
import sys
import time


def interactive(args):
    """Whether a command may stop and ask. A real terminal on stdin, and
    --no-input not given."""
    return sys.stdin.isatty() and not getattr(args, "no_input", False)


def confirm(question, default=False):
    """A yes/no prompt. Returns `default` without a terminal or on EOF."""
    if not sys.stdin.isatty():
        return default
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(question + suffix).strip().lower()
    except EOFError:
        print()
        return default
    if not answer:
        return default
    return answer in ("y", "yes", "o", "oui")


def _parse_selection(raw, count):
    """The 1-based numbers a user typed: "2", "1 3 5", "1-4", "all", mixed.
    Out-of-range or unparseable input returns None."""
    raw = raw.strip().lower()
    if raw in ("all", "*", "tout"):
        return list(range(count))
    picked = []
    for token in raw.replace(",", " ").split():
        if "-" in token[1:]:
            lo, _, hi = token.partition("-")
            try:
                lo, hi = int(lo), int(hi)
            except ValueError:
                return None
            if not (1 <= lo <= hi <= count):
                return None
            picked.extend(range(lo - 1, hi))
        else:
            try:
                n = int(token)
            except ValueError:
                return None
            if not 1 <= n <= count:
                return None
            picked.append(n - 1)
    # De-duplicate, keep order.
    seen, out = set(), []
    for i in picked:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def choose(items, render, prompt, multiple=False, header=None):
    """Show a numbered menu and return the chosen item(s).

    `render` turns an item into its line. With `multiple`, returns a (possibly
    empty) list for ranges / several numbers / "all"; otherwise a single item
    or None. An empty line cancels.
    """
    if not items:
        return [] if multiple else None
    if header:
        print(header)
    for i, item in enumerate(items, 1):
        print(f"  {i:>3}  {render(item)}")
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            print()
            return [] if multiple else None
        if not raw.strip():
            return [] if multiple else None
        if multiple:
            picked = _parse_selection(raw, len(items))
            if picked is None:
                print("  ? a number, a range like 1-4, several, or 'all'")
                continue
            return [items[i] for i in picked]
        try:
            n = int(raw.strip())
        except ValueError:
            print("  ? one number")
            continue
        if 1 <= n <= len(items):
            return items[n - 1]
        print(f"  ? 1 to {len(items)}")


def app_pids():
    """Pids of the running claude-desktop processes, read straight from
    /proc so nothing need be installed just to find them."""
    pids = []
    for entry in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(entry, "rb") as fh:
                if b"claude-desktop" in fh.read():
                    pids.append(int(entry.split("/")[2]))
        except (OSError, ValueError):
            continue
    return pids


def quit_app(timeout=15):
    """Ask the processes to quit (SIGTERM), wait, and SIGKILL whatever is
    left. Returns True once none remain."""
    pids = app_pids()
    if not pids:
        return True
    print(f"quitting claude-desktop ({len(pids)} processes)...")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not app_pids():
            print("claude-desktop quit.")
            return True
        time.sleep(0.3)
    leftover = app_pids()
    if leftover:
        print(f"still up after {timeout}s, forcing...")
        for pid in leftover:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(0.5)
    done = not app_pids()
    print("claude-desktop stopped." if done else "could not stop claude-desktop.")
    return done
