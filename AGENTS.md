# omarchy-spotlight (fork) — agent instructions

Read `docs/FORK.md` in full before touching anything here, every session,
whichever coding agent you are. It says what this fork is for, what is already
upstream, what is still open, and the one rule that makes the whole thing work:
**improvements are written here and offered upstream as PRs.**

This is a fork of [`maajix/omarchy-spotlight`](https://github.com/maajix/omarchy-spotlight).
`origin` is ours, `upstream` is theirs. The upstream maintainer has been fast
and receptive (issues #1 and #2 accepted and fixed within hours), so treat
"send it upstream" as the default outcome of any change, not the exception.

## Working here

- **Never mix fork-only files into a PR branch.** `AGENTS.md`, `docs/FORK.md`
  and `.herdr/` exist for us and mean nothing to upstream. Branch from
  `upstream/main`, not from a branch that carries them.
- One branch and one PR per issue item. They are independent on purpose.
- Rebase on `upstream/main` before opening a PR — upstream moves fast.
- Code and comments in English, like the rest of the codebase. Match the
  surrounding style: this project comments the *why*, densely, and a patch
  that only restates the code will look foreign in it.

## Testing a change (the part that wastes hours if you guess)

The plugin that actually runs is the copy installed at
`~/.config/omarchy/plugins/io.github.maajix.spotlight`, not this checkout.
That copy is git-managed by `omarchy plugin update` and tracks **upstream**, so
anything you paste into it is temporary by design.

- **QML does not hot-reload here.** After changing a `.qml` you must run
  `omarchy-restart-shell`, or you are testing the old code and will conclude
  the wrong thing.
- **The Quickshell log file is unreadable** (`/run/user/1000/quickshell/by-id/*/log.log`
  is encoded v50, the local decoder speaks v2). But `console.log` from QML
  still reaches the journal: `journalctl --user -t omarchy-shell`. That is the
  only working window into the running plugin.
- **To prove a QML `Process` actually fires**, replace `bin/spotlight-helper`
  with a wrapper that appends `sys.argv` to a file and `execv`s the real one.
  Faster and more certain than reading the code.
- The overlay does not always open on the monitor you expect. Find it with
  `hyprctl layers -j | jq '..|.namespace? // empty'` before screenshotting, or
  you will photograph an empty screen and think the feature is broken.
- The helper is testable on its own, with no shell at all:
  `python3 bin/spotlight-helper files "$HOME" <pattern>`.

## Reviewer colleagues

If you are running as `omaspotlight-exec` inside a Herdr workspace,
`omaspotlight-rev-1` (Codex) and `omaspotlight-rev-2` (Claude Opus) are two
independent reviewers alive in sibling panes right now — not hypothetical,
nothing to set up. When you finish a reviewable unit of work, use the
`herdr-review` skill to dispatch a blind, parallel round to both and resolve
their findings (CONFIRMED/UNIQUE/CONFLICT) before calling the work done. The
same pair can weigh in on an open design question *before* you build — that is
the `herdr-ask` skill. Requires `HERDR_ENV=1`; if it is unset you are not in a
Herdr-managed pane and none of this applies. Never substitute your CLI's own
native sub-agent mechanism (Codex `agents`, Claude's `Agent` tool) for this:
those spawn ephemeral processes outside Herdr, with no pane and no persistent
identity. Every round, including a "final" one, goes back through
`herdr-review`.
