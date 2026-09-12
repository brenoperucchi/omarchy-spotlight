# Spotlight

**A fast, local-first command palette for Omarchy, inspired by macOS Spotlight and Raycast.**

Launch apps. Jump to open windows. Find files. Search your clipboard. Run Omarchy commands. Calculate, convert units, create reminders and calendar events, or search the web — all from the same input.

![Spotlight](preview.png)

Spotlight runs directly inside the existing `omarchy-shell` process. Opening it is just an IPC call into something that is already running, so there is no separate launcher to start and no cold-start delay.

The idea is simple: press one shortcut, type what you want, press Enter.

---

## Install

Install and enable Spotlight with:

```bash
omarchy plugin add https://github.com/maajix/omarchy-spotlight.git --enable
```

If you would rather inspect the code before enabling it:

```bash
omarchy plugin add https://github.com/maajix/omarchy-spotlight.git
```

### Add a shortcut

Add this to `~/.config/hypr/bindings.lua`:

```lua
o.bind("ALT + SPACE", "Spotlight", "omarchy-shell shell toggle io.github.maajix.spotlight '{}'")
```

`ALT + SPACE` is unbound on stock Omarchy, but you can use any key combination you prefer.

> Since Spotlight 1.1.3, `ALT + SPACE` is the recommended default. Older versions used `CTRL + SPACE`, which conflicts with fcitx5 on fresh Omarchy installations.

The IPC payload can also contain a query. That means you can create shortcuts that open Spotlight already prepared for a specific task:

```lua
o.bind("ALT + SHIFT + SPACE", "Spotlight reminder",
  "omarchy-shell shell toggle io.github.maajix.spotlight '{\"query\":\"remind me \"}'")
```

### Optional: frosted glass

Spotlight works without any extra visual configuration. By default, the panel is simply translucent.

If you want the frosted-glass look, enable Hyprland blur and apply it to Spotlight in `~/.config/hypr/looknfeel.lua`:

```lua
-- Blur has to be enabled globally before a layer rule can use it.
hl.config({
  decoration = {
    blur = {
      enabled = true,
      size = 8,
      passes = 3,
      brightness = 0.8,
      contrast = 0.9,
      new_optimizations = true
    },
  },
})

hl.layer_rule({
  match = { namespace = "omarchy-spotlight" },
  blur = true,
  ignore_alpha = 0.4,
})
```

Keep `ignore_alpha`: Spotlight's surface is fullscreen, and the threshold makes sure only the card gets blurred.

Then reload Hyprland:

```bash
hyprctl reload
```

---

## One search box, a lot less friction

You do not have to decide which kind of search you are doing before you start typing.

From two characters onward, Spotlight can search local providers together, merge their results, rank them globally, and put the most likely result at the top.

So the same input can find an application, an already-open window, a file, a command, or something from your clipboard.

Press Enter and the selected result performs its primary action.

| Try this | Spotlight does this |
|---|---|
| `chrom` | Finds matching applications alongside other local results |
| `disc` | Finds the app and matching open windows |
| `screenshot` | Finds Omarchy and system actions |
| `lock` | Locks the session |
| `theme` | Finds theme-related actions |
| `12*7+3` | Calculates the result; Enter copies it |
| `sqrt(144)` | Handles common mathematical expressions |
| `20% of 250` | Calculates percentages |
| `15 mod 4` | Handles modulo expressions |
| `10 km to miles` | Converts units offline |
| `72f in c` | Converts temperatures |
| `5 GiB to MB` | Converts data sizes |
| `remind me in 20m to check the oven` | Creates an `omarchy reminder` |
| `remind me tomorrow at 9 to call the dentist` | Understands natural dates and times |
| `reminders` | Shows pending reminders and lets you clear them |
| `meeting with sarah tomorrow at 14:00 for 90min` | Creates a calendar event |
| `f invoice` | Searches files and folders |
| `~/Downloads/` | Searches within a path |
| `/etc/` | Searches an absolute path |
| `cb ssh` | Searches clipboard history; Enter copies the result |
| `gh quickshell` | Searches GitHub |
| `yt lofi` | Searches YouTube |
| `aw hyprland` | Searches ArchWiki |
| `tr what is this to german` | Translates, into the language you name |
| `example.com` | Opens the URL directly |
| `localhost:3000` | Opens the local URL |
| anything else | Offers a web search |

The goal is not to turn Spotlight into a collection of separate mini-tools. It should still feel like one search box.

---

## Search the way you want

Most of the time, just type.

When you do want to be explicit, Spotlight also supports bang searches and provider filters.

### Bang searches

Bang prefixes send your query directly to a specific search destination:

```text
g       Google
ddg     DuckDuckGo
yt      YouTube
gh      GitHub
w       Wikipedia
wde     German Wikipedia
aw      ArchWiki
aur     AUR
pkg     Arch packages
so      Stack Overflow
mdn     MDN
npm     npm
crates  crates.io
docker  Docker Hub
maps    Maps
tr      Translate
img     Images
hn      Hacker News
omarchy Omarchy
```

For example:

```text
gh quickshell
yt lofi
aw hyprland
mdn array map
```

These results can appear alongside local matches, so `gh something` can still surface a matching local application if one exists.

### Search only one provider

Colon filters tell Spotlight to search one provider exclusively:

```text
a:          app:
w:          window:
f:          file:
action:     cmd:
cb:         clipboard:
web:        search:       url:
calc:
unit:       convert:
reminder:
calendar:   event:
```

Examples:

```text
app: firefox
window: github
file: invoice
clipboard: ssh
calc: 125 * 1.19
```

A filter without a query shows a hint instead of launching an unnecessarily broad search.

The space-separated `w query` syntax remains the Wikipedia bang; `w:` is the window filter.

The `tr` bang reads an optional target language off the end of the query, so
`tr what is this to german` translates just `what is this`. `to`, `in` and `into`
all work, and the language can be a name or a code (`german`, `de`, `pt-br`).
Without one it opens English to German. The source language is always
auto-detected, so `tr wie geht es dir to english` goes the other way.

---

## Enter should do what you expect

Search results do not all arrive at the same time.

Applications and actions are usually available immediately. File hits or web suggestions may arrive a few hundred milliseconds later.

Spotlight deliberately prevents those late results from stealing your selection.

If you type an application name quickly and press Enter, you get the application you intended — not the web suggestion or file result that happened to appear underneath the highlight a moment later.

The cursor only moves when you move it:

```text
↑ / ↓
Ctrl+P / Ctrl+N
PageUp / PageDown
```

Pointer movement can also change the selection, but a mouse simply resting above the panel does not. Hover is briefly ignored after each keystroke because the result card can resize while new rows appear.

It is a small detail, but it makes fast keyboard use much more predictable.

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `↑` `↓` | Move through results |
| `Ctrl+P` `Ctrl+N` | Move through results |
| `PageUp` `PageDown` | Move one screen |
| `↵` | Run the primary action shown in the footer |
| `⇧↵` / `Ctrl+↵` | Run the secondary action, when available |
| `Tab` | Complete the query with the selected application's name |
| `Esc` | Clear the query; close Spotlight if the query is already empty |

The search field is a real text input, so normal selection, caret movement, and shortcuts such as `Ctrl+V` work as expected.

Destructive system actions are harder to trigger accidentally: logout, restart, and shutdown require a second `Enter` before Spotlight performs them.

---

## Spotlight gets better at finding *your* result

Spotlight can learn from what you actually choose.

Applications, windows, files, and actions that you use are given a limited ranking bonus based on recency, frequency, and the current query.

That means typing the same few characters repeatedly can gradually favor the result you normally choose, without letting personalization overpower a clearly better text match.

Clipboard results and secondary actions are not learned.

When the search box is empty, Spotlight uses this history to surface useful applications and actions, plus still-present learned files and matching open windows. With no history yet, it simply falls back to applications.

You can disable learning completely:

```json
{
  "learningEnabled": false
}
```

This stops both recording new selections and applying ranking bonuses. Existing learning data is left untouched until you explicitly reset it.

<details>
<summary><strong>How ranking works</strong></summary>

Every provider uses the same text-match stages:

```text
exact
prefix
word
substring
metadata / acronym
residual
```

Results are then ranked globally using:

```text
textMatch × typeWeight + recency + frequency + queryContext
```

Current type weights are:

```text
Intent      1.05
App         1.00
Window      0.98
File        0.96
Action      0.94
Clipboard   0.92
Web         0.80
```

Learning can contribute at most 200 points:

```text
Recency          40
Frequency        50
Query context   110
```

That is intentionally enough to rearrange close results, but not enough for a weak personalized result to beat a substantially better exact match.

Equal scores use deterministic title and stable-ID tie breakers.

Primary app, window, file, and action activations are learned. Clipboard rows and secondary actions are not.

</details>

---

## Reminders without leaving the keyboard

Spotlight understands common natural-language reminder formats:

```text
remind me in 20m to check the oven
remind me in 1h30 to take a break
remind me at 15:30 to call john
remind me friday 9am to send the report
remind me 24.12. 10:00 to buy flowers
```

They are created through `omarchy reminder`.

To see what is pending, search:

```text
reminders
```

Spotlight also provides an action to clear pending reminders.

---

## Calendar events

You can create calendar events with the same natural input:

```text
meeting with sarah tomorrow at 14:00 for 90min
```

The primary action opens the event in Google Calendar.

Use `Shift+Enter` to generate an `.ics` file instead.

---

## File search

Search for files naturally:

```text
invoice
```

Or explicitly restrict the query to files:

```text
f invoice
f: invoice
file: invoice
```

Paths work too:

```text
~/Downloads/
/etc/
```

File results participate in the same global ranking as applications, windows, actions, and other providers unless you use a file-only filter.

---

## Clipboard search

Spotlight can search your local clipboard history:

```text
cb ssh
cb: ssh
clipboard: ssh
```

Press Enter to copy the selected result back to the clipboard.

Only bounded one-line previews are passed to the shell. The full selected clipboard body is sent directly from the helper to `wl-copy`.

---

## Settings

Spotlight works without a configuration file.

If you want to customize it, settings live at:

```text
~/.config/omarchy/spotlight.json
```

The file is re-read every time Spotlight opens, so changes do not require restarting the shell.

A complete configuration looks like this:

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

Search for:

```text
spotlight settings
```

to access Spotlight's own maintenance actions. From there you can create or edit the settings file, open the plugin or data directory, or reset learning.

**Edit Spotlight Settings** only creates the default file when it is missing. It never overwrites an existing configuration.

### Web suggestions

Live web suggestions are disabled by default:

```json
{
  "webSuggestions": false
}
```

When enabled, the current query is sent to Google's public autocomplete endpoint while you type.

The normal web-search result behaves differently: no query is sent anywhere until you activate the row.

`searchEngine` controls where that regular web-search result goes:

```json
{
  "searchEngine": "g"
}
```

It accepts any of the supported bang keys. Live autocomplete suggestions still come from Google.

### Files and clipboard

These providers are enabled by default:

```json
{
  "fileSearch": true,
  "fileSearchAlways": true,
  "clipboardSearch": true,
  "clipboardSearchAlways": true
}
```

With the `Always` options enabled, file and clipboard results join normal searches once the query reaches two characters.

One-character searches only run them when you explicitly use a file or clipboard prefix.

Set the corresponding provider option to `false` to disable that provider completely.

### Result limits

```json
{
  "maxResults": 20,
  "maxApps": 8,
  "maxSuggestions": 4
}
```

`maxResults` controls the size of the combined result list.

Configuration values are validated before Spotlight uses them:

```text
maxApps          3–24
maxSuggestions   0–8
maxResults        8–50
```

`searchEngine` must match a supported bang key, and boolean settings must be actual JSON `true` or `false` values.

Invalid values fall back to their defaults instead of being used.

---

## Local by default

Spotlight does not have telemetry, analytics, or a background network service.

Almost everything happens locally.

| Network access | When it happens |
|---|---|
| `suggestqueries.google.com` | While typing, only if `webSuggestions` is enabled |
| Your browser | When you explicitly activate a web-search, URL, or calendar result |

With the default configuration, live web suggestions are disabled.

The normal search result does not send your query to a search engine in the background. It opens the destination only after you press Enter.

---

## Privacy and security

Spotlight's helper is intentionally narrow.

File and subprocess output is bounded. Persistent files are validated through directory descriptors, unsafe ownership and permissions are rejected, symlinks are refused, and writes are atomic and private.

Subprocesses have deadlines, and their process groups are cleaned up.

Clipboard search exposes only bounded one-line previews to the shell. The complete selected clipboard value goes directly from the helper to `wl-copy`.

When learning is enabled, Spotlight stores the following locally:

```text
selected stable IDs
selection counts
timestamps
file paths
normalized search text
query prefixes starting at two characters
```

Colon filters use separate query-context namespaces.

Learning data lives at:

```text
~/.local/state/omarchy/spotlight-usage.json
```

The store is bounded to 400 items, including at most 100 files, plus 128 query contexts with eight results each and a fixed serialized-byte budget.

File IDs are SHA-256 fingerprints of their paths. Missing files are discarded when the store is read.

V1 launch counts are migrated automatically to V2 stable IDs.

To stop recording and using this data:

```json
{
  "learningEnabled": false
}
```

To remove it, search for **Reset Spotlight Learning**. The action requires a second Enter and deletes only `spotlight-usage.json`.

---

## Requirements

Spotlight targets **Omarchy 4 (Quattro)** with the Quickshell-based `omarchy-shell`.

It only relies on components already present in stock Omarchy:

| Package | Used for |
|---|---|
| `python3` | `bin/spotlight-helper`, which brokers file reads and subprocesses |
| `fd` | File search |
| `wl-clipboard` | Copy actions |

---

## Update

Update Spotlight through Omarchy:

```bash
omarchy plugin update io.github.maajix.spotlight
```

---

## Uninstall

Remove the plugin:

```bash
omarchy plugin remove io.github.maajix.spotlight
```

Then remove any Hyprland configuration you added manually:

- the `o.bind(...)` entry from `~/.config/hypr/bindings.lua`
- the `hl.layer_rule` for `omarchy-spotlight` from `~/.config/hypr/looknfeel.lua`

You can leave the global `hl.config` blur configuration in place if something else uses it.

After changing Hyprland configuration:

```bash
hyprctl reload
```

Spotlight may also leave its optional settings and local ranking history behind. Remove them if you want a completely clean uninstall:

```bash
rm -f ~/.config/omarchy/spotlight.json
rm -f ~/.local/state/omarchy/spotlight-usage.json
```

---

## Development

The project is split into three main pieces:

```text
Spotlight.qml          UI and actions
lib/                   JavaScript parsers and ranking logic
bin/spotlight-helper   Bounded interface to files and subprocesses
```

Because the plugin stays loaded inside `omarchy-shell`, restart the shell after changing QML.

Useful checks before committing:

```bash
omarchy plugin validate .
python3 -m py_compile bin/spotlight-helper
/usr/lib/qt6/bin/qmlformat -n Spotlight.qml >/dev/null
for file in lib/*.js; do node --check "$file"; done
```

---

## License

MIT — see [LICENSE](LICENSE).

Spotlight is not affiliated with Apple or Raycast.
