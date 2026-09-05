# Spotlight

A command palette for [Omarchy](https://omarchy.org/), in the shape of macOS
Spotlight and Raycast. It runs inside the existing `omarchy-shell` process, so
opening it is an IPC call into something already running rather than a cold
start.

![Spotlight](preview.png)

Apps, open windows, Omarchy commands, a calculator, offline unit conversion,
natural-language reminders, calendar events, file search, clipboard history and
web search — one input, ranked so the top row is the one you meant.

## Install

```bash
omarchy plugin add https://github.com/maajix/omarchy-spotlight.git
omarchy plugin enable io.github.maajix.spotlight
```

`omarchy plugin add` clones the repository to
`~/.config/omarchy/plugins/io.github.maajix.spotlight/` and leaves it disabled
so you can read the code first. Enabling adds the id to `plugins[]` in
`~/.config/omarchy/shell.json`.

Nothing else is written for you. The two steps below edit your Hyprland config,
so they are yours to paste in.

### 1. A key to open it

In `~/.config/hypr/bindings.lua`. `CTRL + SPACE` is unbound on stock Omarchy;
pick anything you like:

```lua
o.bind("CTRL + SPACE", "Spotlight", "omarchy-shell shell toggle io.github.maajix.spotlight '{}'")
```

The payload may carry a query, so a second key can open it already primed:

```lua
o.bind("CTRL + SHIFT + SPACE", "Spotlight reminder",
  "omarchy-shell shell toggle io.github.maajix.spotlight '{\"query\":\"remind me \"}'")
```

### 2. Frosted glass (optional)

Without this the panel is simply translucent, which works fine. For the frosted
look, in `~/.config/hypr/looknfeel.lua`:

```lua
-- Blur has to be on globally before any layer rule can use it.
hl.config({
  decoration = {
    blur = { enabled = true, size = 8, passes = 3, brightness = 0.8, contrast = 0.9, new_optimizations = true },
  },
})

hl.layer_rule({
  match = { namespace = "omarchy-spotlight" },
  blur = true,
  ignore_alpha = 0.4,
})
```

`ignore_alpha` is not optional here. The plugin's layer surface is fullscreen —
a dim scrim with the card floating in it — so `blur = true` on its own frosts
your entire desktop. The threshold is what keeps the blur on the card:

```
card  alpha 0.62  >  0.4  ->  blurred, reads as glass
scrim alpha 0.25  <  0.4  ->  untouched, only dims
```

Then `hyprctl reload`.

> Turning on global blur affects every layer rule you already have. If another
> plugin sets `blur = true` on a fullscreen surface without `ignore_alpha`, that
> plugin will now frost the whole screen. Check with `hyprctl layers`.

## Uninstall

```bash
omarchy plugin disable io.github.maajix.spotlight
omarchy plugin remove io.github.maajix.spotlight
```

Then delete what you pasted in by hand:

- the `o.bind(...)` line in `~/.config/hypr/bindings.lua`
- the `hl.layer_rule` block for `omarchy-spotlight` in `~/.config/hypr/looknfeel.lua`
  (leave the `hl.config` blur block if anything else uses it), then `hyprctl reload`

And, if you made them, two files the plugin owns and nothing else reads:

```bash
rm -f ~/.config/omarchy/spotlight.json            # your settings, if you wrote one
rm -f ~/.local/state/omarchy/spotlight-usage.json # launch counts, for frecency
```

## What it answers

Providers run in this order, and the top row is preselected, so Enter does the
obvious thing:

| Type this | You get |
|---|---|
| `chrom` | Applications, ranked by how well the name matches and then by frecency |
| `disc` | …plus any open window whose title or app id matches |
| `screenshot`, `lock`, `theme` | Omarchy and system commands |
| `12*7+3`, `sqrt(144)`, `20% of 250`, `15 mod 4` | Calculator — Enter copies the result |
| `10 km to miles`, `72f in c`, `5 GiB to MB` | Offline unit conversion |
| `remind me in 20m to check the oven` | Sets an `omarchy reminder` |
| `remind me tomorrow at 9 to call the dentist` | Natural times: `in 1h30`, `at 15:30`, `friday 9am`, `24.12. 10:00` |
| `reminders` | Lists what is pending, with a row to clear them |
| `meeting with sarah tomorrow at 14:00 for 90min` | Calendar event → Google Calendar, or ⇧↵ for an `.ics` file |
| `f invoice`, `~/Downloads/`, `/etc/` | File and folder search |
| `cb ssh` | Clipboard history search — Enter copies |
| `gh quickshell`, `yt lofi`, `aw hyprland` | Bang searches, below any application that also matched |
| `example.com`, `localhost:3000` | Opens the URL |
| anything else | Live web suggestions, then "Search Google for …" |

Bang prefixes: `g` `ddg` `yt` `gh` `w` `wde` `aw` `aur` `pkg` `so` `mdn` `npm`
`crates` `docker` `maps` `tr` `img` `hn` `omarchy`.

## Ranking

Applications are scored by the shell's own `AppSearch` — an exact name, a name
that starts with the query, a name that contains it, then the id, the keywords
and the acronym, each its own tier — and then nudged by **frecency**: the
launch count decayed by how long ago the last launch was, the way `z` and
zoxide rank directories. Two launches this morning outrank forty from last
spring.

The nudge is bounded and it saturates, so it only ever reorders apps that
matched about as well as each other. No amount of usage moves an app past one
whose name starts with what you typed — `stea` is Steam on a fresh install and
still Steam after a thousand launches of something else. On an empty query
there is no match to respect, so the list is pure frecency: your most-used apps,
most-used first.

Commands and quicklinks are ranked the same way.

## The cursor

The top row is selected, and it stays selected as the list changes underneath
it. Async rows — web suggestions, file hits — land a few hundred milliseconds
after the keystroke that asked for them, and none of them may take the cursor:
type an app name at speed and press Enter and you get the app, never the web
search that happened to be under the highlight.

The cursor only moves where you put it — `↑` `↓`, `PageUp` `PageDown`, or a
pointer that actually travelled. A pointer resting over the panel does not
count, and hover is ignored for a moment after each keystroke, because the card
resizes as results arrive and rows slide under a still mouse.

## Keys

| Key | Action |
|---|---|
| `↑` `↓`, `Ctrl+P` `Ctrl+N` | Move |
| `PageUp` `PageDown` | Move a screen |
| `↵` | Primary action, named in the footer |
| `⇧↵` / `Ctrl+↵` | Secondary action, where one exists |
| `Tab` | Complete the query with the selected app's name |
| `Esc` | Clear the query; on an empty query, close |

Log out, restart and shut down ask for a second `↵` before they act. The text
field is a real input, so `Ctrl+V`, selection and caret movement work normally.

## Settings

Optional, at `~/.config/omarchy/spotlight.json`. It hot-reloads; the plugin
never writes to it.

```json
{
  "webSuggestions": true,
  "searchEngine": "g",
  "fileSearch": true,
  "maxApps": 8,
  "maxSuggestions": 4
}
```

**`webSuggestions` is on by default and sends your query to Google's public
autocomplete endpoint as you type.** Set it to `false` to keep every keystroke
on your machine; the "Search Google for …" row still works, because it only
opens a URL. `searchEngine` takes any bang key above, so `"ddg"` makes
DuckDuckGo both the fallback and the suggestion source.

Launch counts live in `~/.local/state/omarchy/spotlight-usage.json` — one
`{count, last}` per app, command and bang, capped at 400 entries. Delete it to
forget the ranking.

## What it talks to

| Goes out | When | Turn it off with |
|---|---|---|
| `suggestqueries.google.com` | Each query, debounced, while `webSuggestions` is on | `"webSuggestions": false` |
| Your browser, to a search or calendar URL | Only when you press Enter on such a row | — |

Everything else is local. No telemetry, no analytics, no background network.

## Requirements

Omarchy 4 (Quattro) with the Quickshell-based `omarchy-shell`. These are all
part of a standard Omarchy install; a missing one only disables its feature:

| Package | Used for |
|---|---|
| `curl` | Web suggestions |
| `fd` | File search |
| `wl-clipboard` | The copy actions |

## Hacking on it

`Spotlight.qml` is the surface and the only place an action turns into an
effect. `lib/` is pure logic, all of it runnable under plain node:

| File | Job |
|---|---|
| `Calc.js` | Recursive-descent arithmetic parser. Deliberately not `eval()` — the query is untrusted and this runs inside the shell process. |
| `Units.js` | Unit families and conversion |
| `NaturalTime.js` | "in 20m", "tomorrow at 9", durations, ICS timestamps |
| `Web.js` | Bangs, URL detection, suggestion parsing |
| `Fuzzy.js` | Ranking for everything that is not an application |
| `Frecency.js` | Decayed launch counts — how often, weighted by how recently |
| `Commands.js` | The command and quicklink catalogue — plain data |

Applications are matched by the shell's own `AppLibrary`, so they match the same
way as the Omarchy menu; only the frecency nudge on top is this plugin's.
Colors come from the active theme's `[menu]` tokens, so the panel rethemes with
everything else.

**The plugin is `keepLoaded`, so saving a `.qml` file is not enough to see the
change.** The shell reloads the component but keeps the instance it already
mounted, and you end up testing the old build. Run `omarchy restart shell`
after editing.

Static check, without starting a shell:

```bash
mkdir -p /tmp/imports && ln -sfn /usr/share/omarchy/shell /tmp/imports/qs
/usr/lib/qt6/bin/qmllint -I /tmp/imports -I /usr/lib/qt6/qml Spotlight.qml
```

On Qt 6.11.2 `qmllint` segfaults on a file this size — on any commit, so a
crash there says nothing about your edit. `qmlformat -n Spotlight.qml` still
parses it, and the `lib/` modules run under plain node:

```bash
/usr/lib/qt6/bin/qmlformat -n Spotlight.qml > /dev/null
node --check lib/Frecency.js
```

## License

MIT — see [LICENSE](LICENSE).

Not affiliated with Apple or Raycast.
