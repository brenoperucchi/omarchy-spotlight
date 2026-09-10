# omarchy-spotlight (fork) — what this is

> Process, workflow and stack — how to test a change, how PRs go upstream, who
> reviews — live in **`AGENTS.md`**. Read it too; only one of these two files
> is loaded automatically by whichever CLI you are (Claude loads `CLAUDE.md`,
> which is a symlink to this file; Codex loads `AGENTS.md`).

## Why this fork exists

Fork of [`maajix/omarchy-spotlight`](https://github.com/maajix/omarchy-spotlight),
created 2026-09-10 from `main` at 1.1.4.

**It is not a divergence.** It is the bench where changes get written and
tested before being offered upstream as PRs. What upstream takes, we drop from
the fork and pull back from `upstream/main`. What upstream declines stays here
and keeps working for us. Either outcome is fine; only carrying a patch we
never offered is not.

The reason to say this out loud: the maintainer accepted issues #1 and #2 and
shipped both within hours of them being filed. A fork that quietly hoards fixes
against a maintainer like that would be worse for us than no fork at all — we
would be maintaining a permanent rebase for nothing.

## Reference

The target is macOS Spotlight, which the plugin already models itself on. When
a behaviour here is up for debate, "what does Spotlight do" is a real argument,
not a rhetorical one.

## Already upstream (nothing to do)

- **#1** — Enter on a file result did nothing. `xdg-open` both mis-resolved the
  MIME type (it asks `xdg-mime query filetype`, which falls back to
  `file --mime-type` and ignores the extension unless `perl-file-mimeinfo` is
  installed) and could not launch a `Terminal=true` handler. Fixed upstream in
  `9667c62` by switching to `gio open`, which gets both right.
- **#2** — the *Files* section ranked eighth even behind the explicit `f `
  prefix, and the README recommended `CTRL + SPACE`, which collides with
  fcitx5's default `TriggerKey` (fcitx5 ships with Omarchy and is enabled on
  first run). Fixed in `c482288`.

## Open — [issue #3](https://github.com/maajix/omarchy-spotlight/issues/3)

Three items, independent, one branch and one PR each.

### 1. Multi-term queries match nothing

`bin/spotlight-helper` passes the whole query to `fd` as a single pattern, so
anything with a space matches nothing. `f PMJ XLS` cannot find
`PMJ Analise Investimentos.xlsx`, because no filename contains the literal
string `PMJ XLS`. macOS Spotlight ANDs the terms, which is what makes
"name + extension" the natural way to narrow a search.

`fd` has had this natively since 9.0 (verified on 10.5.0):

```
$ fd -- "PMJ XLS"                 # nothing
$ fd --and "xls" -- "PMJ"
/home/…/docs/PMJ Analise Investimentos.xlsx
```

Split the pattern on whitespace: first token stays the pattern, the rest become
`--and <token>`. Single-term queries are unaffected. Cap the token count, and
remember the tokens are user data going into a regex — the existing escaping
still applies.

### 2. Files are unreachable without a prefix

`fileSearchTarget()` in `Spotlight.qml` only matches `f `/`file `/`files ` or a
path starting with `~/` or `/`. Every other query never touches file search at
all.

Spotlight has no prefix — files are one result group among others for any
query. The prefix is genuinely good for *scoping* to files only (that is what
#2 turned it into), but requiring it to *reach* files means you must already
know that what you want is a file before you start typing.

Run the file search on ordinary queries too and keep the prefix as the
files-only scope it now is. If the per-query `fd` run is the objection, a
setting (`fileSearchAlways`, default off) at least makes it reachable. The
helper already bounds every run with `--max-results`, a byte ceiling and a
wall-clock deadline.

### 3. `WlrKeyboardFocus.Exclusive` traps the compositor's keybinds

`Spotlight.qml` declares the layer surface as
`WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive`. With the overlay
open, Hyprland's own window-focus binds go dead and the overlay never yields.
Measured on this machine, same key, same two windows on the workspace:

| | `SUPER + RIGHT` | overlay after |
| --- | --- | --- |
| overlay closed | focus moves (`DRE` → `hyprsession-lab`) | — |
| overlay open | nothing happens | still open |

Anything that moves focus elsewhere should dismiss the launcher — that is what
Spotlight does, and what every launcher user expects. Wanted:
`WlrKeyboardFocus.OnDemand` plus a dismiss on focus loss. Typing keeps working;
the compositor gets its job back.

## Related work in this workspace

The plugin's *installed* copy lives at
`~/.config/omarchy/plugins/io.github.maajix.spotlight` and is updated with
`omarchy plugin update` from **upstream**. Local edits there are for testing
and get overwritten. The test loop and its traps are in `AGENTS.md`.
