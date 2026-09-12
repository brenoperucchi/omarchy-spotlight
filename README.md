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
omarchy plugin add https://github.com/maajix/omarchy-spotlight.git --enable
```

Omit `--enable` if you want to inspect the code before enabling the plugin.

The two optional steps below are manual changes to your Hyprland configuration.

### 1. A key to open it

In `~/.config/hypr/bindings.lua`. `ALT + SPACE` is unbound on stock Omarchy;
pick anything you like:

```lua
o.bind("ALT + SPACE", "Spotlight", "omarchy-shell shell toggle io.github.maajix.spotlight '{}'")
```

The payload may carry a query, so a second key can open it already primed:

```lua
o.bind("ALT + SHIFT + SPACE", "Spotlight reminder",
  "omarchy-shell shell toggle io.github.maajix.spotlight '{\"query\":\"remind me \"}'")
```

> As of version 1.1.3, the recommended keybind uses `ALT + SPACE`. Earlier
> versions suggested `CTRL + SPACE`, which conflicts with fcitx5 on fresh
> Omarchy installations.

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

Keep `ignore_alpha`: the surface is fullscreen, and the threshold limits blur
to the card. Then run `hyprctl reload`.

## Update

```bash
omarchy plugin update io.github.maajix.spotlight
```

## Uninstall

```bash
omarchy plugin remove io.github.maajix.spotlight
```

Then delete what you pasted in by hand:

- the `o.bind(...)` line in `~/.config/hypr/bindings.lua`
- the `hl.layer_rule` block for `omarchy-spotlight` in `~/.config/hypr/looknfeel.lua`
  (leave the `hl.config` blur block if anything else uses it), then `hyprctl reload`

The plugin may also leave its optional settings and local ranking history:

```bash
rm -f ~/.config/omarchy/spotlight.json            # your settings, if you wrote one
rm -f ~/.local/state/omarchy/spotlight-usage.json # local ranking data
```

## What it answers

Local providers run together from two characters, then their rows are globally
ranked and capped. The top row is preselected, so Enter does the obvious thing:

| Type this | You get |
|---|---|
| `chrom` | Matching applications alongside other local result types |
| `disc` | …plus any open window whose title or app id matches |
| `screenshot`, `lock`, `theme` | Omarchy and system commands |
| `12*7+3`, `sqrt(144)`, `20% of 250`, `15 mod 4` | Calculator — Enter copies the result |
| `10 km to miles`, `72f in c`, `5 GiB to MB` | Offline unit conversion |
| `remind me in 20m to check the oven` | Sets an `omarchy reminder` |
| `remind me tomorrow at 9 to call the dentist` | Natural times: `in 1h30`, `at 15:30`, `friday 9am`, `24.12. 10:00` |
| `reminders` | Lists what is pending, with a row to clear them |
| `meeting with sarah tomorrow at 14:00 for 90min` | Calendar event → Google Calendar, or ⇧↵ for an `.ics` file |
| `f invoice`, `f: invoice`, `~/Downloads/`, `/etc/` | File and folder search; a prefix scopes results to files only |
| `cb ssh`, `cb: ssh` | Clipboard history search — Enter copies |
| `gh quickshell`, `yt lofi`, `aw hyprland` | Bang searches, below any application that also matched |
| `example.com`, `localhost:3000` | Opens the URL |
| anything else | A web-search row; optional live suggestions appear when enabled |

Bang prefixes: `g` `ddg` `yt` `gh` `w` `wde` `aw` `aur` `pkg` `so` `mdn` `npm`
`crates` `docker` `maps` `tr` `img` `hn` `omarchy`.

Colon filters run one provider exclusively: `a:`/`app:`, `w:`/`window:`,
`f:`/`file:`, `action:`/`cmd:`, `cb:`/`clipboard:`,
`web:`/`search:`/`url:`, `calc:`, `unit:`/`convert:`, `reminder:`, and
`calendar:`/`event:`. A filter without text shows a hint and does not launch a
broad search. The space-separated `w query` remains the Wikipedia bang.

## Ranking

Every provider uses the same match stages: exact, prefix, word, substring,
metadata/acronym, then residual. The global score is:

```text
textMatch × typeWeight + recency + frequency + queryContext
```

Type weights are Intent 1.05, App 1.00, Window 0.98, File 0.96, Action 0.94,
Clipboard 0.92 and Web 0.80. Learning contributes at most 200 points: 40 for
recency, 50 for frequency and 110 for the current query context. That is enough
to swap adjacent match stages, but an exact result still beats a substantially
weaker fully personalized match. Equal scores use deterministic title and
stable-id tie breaks.

Primary app, window, file and action activations learn. Clipboard rows and
secondary actions do not. Empty search mixes learned apps and actions with
still-present learned files and matching open windows; without history it falls
back to applications.

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

Optional, at `~/.config/omarchy/spotlight.json`. It is re-read every time you
open Spotlight. **Edit Spotlight Settings** creates the default file only when
it is missing and never overwrites an existing one.

```json
{
  "webSuggestions": false,
  "searchEngine": "g",
  "fileSearch": true,
  "fileSearchAlways": true,
  "clipboardSearch": true,
  "clipboardSearchAlways": true,
  "learningEnabled": true,
  "maxResults": 20,
  "maxApps": 8,
  "maxSuggestions": 4
}
```

`webSuggestions` is off by default. Enabling it sends the query to Google's
public autocomplete endpoint as you type. The regular web-search row only opens
a URL after activation. `searchEngine` accepts any bang key above and controls
that row's destination; live suggestions still come from Google.

`fileSearchAlways` and `clipboardSearchAlways` are on by default, so both local
providers join every query of at least two characters. Their corresponding
`fileSearch` and `clipboardSearch` switches disable the provider completely.
One-character searches run them only through an explicit file or clipboard
prefix. `maxResults` caps the combined list and accepts 8–50.

`learningEnabled: false` stops both recording and ranking bonuses without
deleting existing data.

Every value is range-checked on the way in and a bad one falls back to its
default rather than being used: `maxApps` is clamped to 3–24, `maxSuggestions`
to 0–8, `maxResults` to 8–50, `searchEngine` has to name an engine in the bang
table, and booleans have to be real JSON `true`/`false`.

Search `spotlight settings` to create and edit this file, open the plugin or
data folder, or reset Spotlight learning. Reset requires a second Enter and
deletes only `spotlight-usage.json`.

Learning data lives in `~/.local/state/omarchy/spotlight-usage.json`. V1 launch
counts migrate automatically to V2 stable IDs. The store is capped at 400
items, including at most 100 files, plus 128 query contexts with eight results
each and a fixed serialized-byte budget. File IDs are SHA-256 fingerprints of
their paths; missing files are discarded when the store is read.

## What it talks to

| Goes out | When | Turn it off with |
|---|---|---|
| `suggestqueries.google.com` | Each query, debounced, while `webSuggestions` is on | `"webSuggestions": false` |
| Your browser, to a search or calendar URL | Only when you press Enter on such a row | — |

Everything else is local. No telemetry, no analytics, no background network.

## Requirements

Omarchy 4 (Quattro) with the Quickshell-based `omarchy-shell`. Spotlight uses
only components present in stock Omarchy:

| Package | Used for |
|---|---|
| `python3` | `bin/spotlight-helper`, which brokers every file read and subprocess |
| `fd` | File search |
| `wl-clipboard` | The copy actions |

## Privacy and security

The plugin has no telemetry or background service. Its helper bounds file and
subprocess output, validates persistent files through directory descriptors,
refuses symlinks and unsafe ownership or permissions, and uses atomic private
writes. Subprocesses have deadlines and their process groups are cleaned up.
Clipboard search sends only bounded one-line previews to the shell; the full
selected body goes directly from the helper to `wl-copy`.

When learning is enabled, selected stable IDs, counts, timestamps, file paths,
and the normalized search text and its prefixes from two characters are stored
locally. Colon filters use separate context namespaces. Set `learningEnabled`
to `false` to stop using or adding this data, or run **Reset Spotlight
Learning** to delete it.

## Development

`Spotlight.qml` contains the UI and actions. `lib/` contains the JavaScript
parsers and ranking logic. `bin/spotlight-helper` is the bounded interface to
files and subprocesses. Restart the shell after QML changes because the plugin
is kept loaded.

```bash
omarchy plugin validate .
python3 -m py_compile bin/spotlight-helper
/usr/lib/qt6/bin/qmlformat -n Spotlight.qml >/dev/null
for file in lib/*.js; do node --check "$file"; done
```

## License

MIT — see [LICENSE](LICENSE).

Not affiliated with Apple or Raycast.
