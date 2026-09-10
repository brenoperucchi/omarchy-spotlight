# omarchy-spotlight (fork) — process, workflow, stack

**Read `INSTRUCTION.md` first, every session.** It is the context: what this
fork is for, what is already upstream, what is still open. This file is only
the *how* — how to test, how a change becomes a PR, who reviews it.

Do not assume the other file was loaded for you: each CLI loads exactly one of
these automatically. Claude loads `CLAUDE.md` (a symlink to `INSTRUCTION.md`)
and never reads this one on its own; Codex loads this one and never reads
`INSTRUCTION.md` on its own. Verified on Claude Code 2.1.266 — an `AGENTS.md`
alone is invisible to it unless something tells it to go read the file.

This is a fork of [`maajix/omarchy-spotlight`](https://github.com/maajix/omarchy-spotlight).
`origin` is ours, `upstream` is theirs. The upstream maintainer has been fast
and receptive (issues #1 and #2 accepted and fixed within hours), so treat
"send it upstream" as the default outcome of any change, not the exception.

## Working here

- **Never mix fork-only files into a PR branch.** `AGENTS.md`,
  `INSTRUCTION.md`, `CLAUDE.md` and `.herdr/` exist for us and mean nothing to
  upstream. `README.md` is theirs — it is the plugin's own README and changes
  to it are a PR like any other, not a place for fork notes. Branch from
  `upstream/main`, not from a branch that carries them.
- One branch and one PR per issue item. They are independent on purpose.
- Rebase on `upstream/main` before opening a PR — upstream moves fast.
- Code and comments in English, like the rest of the codebase. Match the
  surrounding style: this project comments the *why*, densely, and a patch
  that only restates the code will look foreign in it.

## Testing a change (the part that wastes hours if you guess)

The plugin that actually runs is the copy installed at
`~/.config/omarchy/plugins/io.github.maajix.spotlight`, not this checkout. It
is a real git checkout, and as of 2026-09-10 its `origin` points at **our
fork**, not upstream — this machine's daily-driver Spotlight runs our `main`,
fixes included, rather than waiting on upstream to accept each PR. Anything
you paste into it for a quick check is still temporary by design; the durable
way to update it is landing the fix in this checkout's `main` (see below) and
pulling that into the installed copy.

Our fork's `main` is not upstream's `main`: every fix that gets its own
branch/PR (per the one-branch-one-PR rule above) also gets merged into this
checkout's `main` right away, whether or not upstream has accepted the PR
yet. That is what makes `main` here the thing worth installing — the fork is
the bench *and* the thing we actually run. When upstream accepts a PR and
this fork rebases past it, nothing here changes; the fix was already in
`main` before that happened.

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
