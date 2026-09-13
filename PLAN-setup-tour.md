# Spotlight: First-run Setup Tour

## Context

Spotlight (`~/.config/omarchy/plugins/io.github.maajix.spotlight`, v1.2.4) has no onboarding. A new user installs it, has to hand-edit `~/.config/hypr/bindings.lua` for a shortcut, and never learns that web suggestions, clipboard search, file search and local learning are settings in a JSON file they edit by hand. The tour fixes that: on the very first open it walks through four skippable steps (welcome, shortcut, search sources, try it), persists the choices, and is re-runnable from a new "Run Setup Tour" action next to "Edit Spotlight Settings".

The mockup the user provided is the visual reference. Its gold accent is the user's theme foreground; Spotlight pulls every color from the Omarchy theme singletons, so the tour follows the theme automatically.

## Decisions already made (do not reopen)

- **Branch:** new branch `feat/setup-tour` off `main`. Commit prefix `FEAT:`.
- **UI language:** English.
- **Shortcut step writes `bindings.lua` automatically** (managed marker block at EOF, old hand-written Spotlight line commented out, `hl.unbind` only when the chord is currently bound), then `hyprctl reload`. Verified: Omarchy's `bootstrap.lua` clears `package.loaded` for `hypr.*`, so reload re-evaluates `bindings.lua`.
- **Presets + live recorder.** Presets: `ALT + SPACE` (recommended, free on stock Omarchy), `SUPER + SPACE` (replaces the Omarchy menu), `CTRL + ALT + SPACE` (free). The mockup's `SUPER + K` is dropped, it is Omarchy's keybindings viewer. Recorder hint: chords Hyprland already binds never reach the window.
- **Shortcut handling is a complete, reversible loop (user requirement):** detect the current shortcut, detect conflicts, show the existing owner of a chord, set the shortcut, and undo the change. Undo = helper `revert-binding` removes the managed block and re-enables the previously disabled hand-written line (marked with a distinctive `-- spotlight-tour:disabled ` prefix, never a plain `-- `), then `hyprctl reload`. Step 2 shows "Undo" after a write and "Restore <previous>" when a managed block exists.
- **Second maintenance action "Change Spotlight Shortcut"** opens the tour directly at step 2 in single-step mode (no dots, no Back, "Done" instead of "Continue", does not touch `setupCompleted`). Nobody should have to open the README or edit Lua by hand again.
- **The managed block only replaces the bare toggle bind** (`'{}'` payload). A pre-primed bind like the README's `{"query":"remind me "}` is a different shortcut and stays untouched.
- **Custom file-search roots / recursion are OUT of scope.** File search runs from `$HOME` today; roots are a separate feature.
- **Step 3 toggles map to real settings only:** `fileSearch` + `fileSearchAlways`, `clipboardSearch`, `webSuggestions` + `searchEngine`, `learningEnabled`. Apps, windows, commands are always on (info line, no toggle).
- **Step 4 is not a mocked result list.** Clickable example queries close the tour and land in the real search input.
- **Skip and Finish both set `setupCompleted: true`.** Existing users see the tour once after upgrading (flag is new). Acceptable.
- **Tour lives in a separate `SetupTour.qml`** beside `Spotlight.qml` (implicit same-directory type; the installed `blizl.voxtype-osd` plugin already uses this pattern with 5 files).

## Flow

| Step | Title | Content | Primary / secondary |
|---|---|---|---|
| 1 | Welcome to Spotlight | 3 bullets: Search everything · Do things inline (calc, units, reminders, translate, web) · Keyboard-first | Get started / Skip tour |
| 2 | Choose your shortcut | "Currently bound to CTRL + SPACE" or "No shortcut yet"; 3 preset chips with conflict hints from live Hyprland bindings; recorder field; "Keep current" path | Continue (writes bind + reload) / Back |
| 3 | What should Spotlight search? | Toggle rows: Files & folders (+ sub-toggle "also without `f` prefix"), Clipboard history, Web suggestions (+ engine dropdown, explains data leaves the machine, default off), Learning ("stays on this machine"); info line "Apps, windows and commands are always searchable." | Continue (write-settings) / Back |
| 4 | Try it | 5-6 example-query chips (`firefox`, `f invoice`, `12*1.19`, `5 km in mi`, `remind me tomorrow 9am standup`, `tr hallo welt en`); key legend ↵ · Ctrl+↵ · Tab · Esc | Finish / Back |

Dot progress indicator on every step, "Skip tour" always visible.

## Facts the implementation relies on

- Settings file `~/.config/omarchy/spotlight.json`, all I/O via `bin/spotlight-helper`. Today only `read-settings` and `ensure-settings` (O_EXCL, never overwrites) exist. `normalize_settings` at `bin/spotlight-helper:586`.
- `COMMANDS` allowlist at `bin/spotlight-helper:1564`; `write-usage` (~1286) is the stdin-JSON-write precedent; `write_atomic` (~385), `walk()` (~285), `Denied`.
- Spotlight.qml: `open()` ~215, `refreshSettings()` ~280, `loadSettings()` ~406, `settings` default literal ~155, `Keys.onPressed` on `input` ~1813, maintenance dispatch `spotlight-settings` ~1182 / `spotlight-reset` ~1203, `maintenanceProc` ~1576, `PanelWindow { id: panel }` ~1632, `card` ~1713, `contentHeight` ~2100.
- `lib/Commands.js:12-15` spotlight maintenance rows (`kind: "spotlight-*"`).
- Shell kit for UI: `/usr/share/omarchy/shell/Ui/` (`Button`, `Toggle`, `ToggleSwitch`, `Dropdown`, `PanelHero`, `PanelSectionHeader`, `PanelSeparator`, `TextField`); theme via `qs.Commons` `Color`/`Style`/`Util`; full-screen overlay precedent `SpeedTestOverlay.qml`.
- `omarchy-menu-keybindings --print` lists live bindings as `SUPER SHIFT CTRL + SPACE   → Theme menu`.
- `hl.unbind(chord)` is Hyprland's native Lua API; `o.bind(keys, description, dispatcher)` at `/usr/share/omarchy/default/hypr/helpers.lua:92`.
- `qmllint` segfaults on Spotlight.qml (known). Parse check: `qmlformat -n <file> > /dev/null`; JS: `node --check lib/*.js`.
- Tests: `python -m unittest -v tests/helper_test.py`, `node --test tests/*.test.js` (CI runs the same).

## Implementation

### Part A: helper (`bin/spotlight-helper`) + tests

Line anchors refer to the current file (1599 lines). All new code follows the existing posture: `walk()` for dir fds, `read_file`/`write_atomic`, `Denied` for user-facing errors, `run_bounded` for subprocesses, argv never a shell string.

**A1. Constants** (new `# --- bindings` group after `ICS_STAMP_RE`, ~108):

```python
BINDINGS_BYTES = 256 * 1024          # bindings.lua read cap
BINDINGS_PRINT_BYTES = 64 * 1024     # omarchy-menu-keybindings --print cap (13.7 KB today)
BINDINGS_PRINT_DEADLINE = 3.0
BINDINGS_PRINT_COUNT = 1000
BINDINGS_DESC_CHARS = 120
MARK_START = '-- >>> spotlight setup tour (managed; rerun via "Run Setup Tour") >>>'
MARK_END = "-- <<< spotlight setup tour <<<"
DISABLED_PREFIX = "-- spotlight-tour:disabled "
# Live Spotlight toggle line, hand-written or managed. Group 1 = chord literal.
# Only the bare toggle ('{}' or no payload); a '{"query":…}' payload is a different shortcut, keep it.
TOGGLE_RE = re.compile(
    r'''^\s*o\.bind\(\s*"([^"]+)"\s*,.*omarchy-shell shell toggle io\.github\.maajix\.spotlight'''
    r'''(?:\s*'\{\}')?\s*"\s*[,)]''')
CHORD_MODS = ("SUPER", "CTRL", "ALT", "SHIFT")
CHORD_RE = re.compile(
    r"^(?:SUPER \+ )?(?:CTRL \+ )?(?:ALT \+ )?(?:SHIFT \+ )?"
    r"(?:[A-Z0-9]|SPACE|RETURN|TAB|F(?:[1-9]|1[0-2])|UP|DOWN|LEFT|RIGHT|BACKSPACE|DELETE|PRINT)$")
```
"At least one modifier" is `"+" in chord`; the regex already forces canonical order and single spaces.

**A2. Changed primitives**
- `write_atomic(dirfd, name, payload, mode=0o600)` (~385): add the `mode` param, `os.fchmod(fd, mode)` on the temp fd before `os.replace`. Default keeps every existing caller and the 0600 test unchanged. Reason: `bindings.lua` is 0644 today.
- `normalize_settings` (~586): add `"setupCompleted": False` to the defaults and `out["setupCompleted"] = clamp_bool(parsed.get("setupCompleted"), False)`.

**A3. Private helpers** (after `cmd_write_ics`, before `COMMANDS` ~1563)
- `_hypr_dir()`: `walk([".config","hypr"])`, never `create=True`; `FileNotFoundError` becomes `Denied("~/.config/hypr is missing")`.
- `_file_mode(dirfd, name, default=0o644)`: `S_IMODE` of the existing file so a rewrite keeps its mode.
- `_canon_chord(text)`: split on `[\s+]+`, upper-case, exactly one non-modifier token, rebuild as `SUPER + CTRL + ALT + SHIFT + KEY` order. `"SUPER SHIFT CTRL + SPACE"` and `"ctrl+space"` normalize; `"SUPER + A + B"` returns `None`.
- `_bound_chords()`: `run_bounded(["omarchy-menu-keybindings","--print"], BINDINGS_PRINT_BYTES, BINDINGS_PRINT_DEADLINE)`; `Denied` (tool missing) returns `{}`; drop last line when truncated (same as `cmd_files`); each line `left → desc` (U+2192) becomes `{canon_chord: clamp_text(desc, 120)}`, first wins.
- `_strip_managed(text)`: returns `(lines_without_block, had_block)`; also drops the single blank line written before `MARK_START`; an unclosed block raises `Denied("managed block in bindings.lua is not closed")`. Use `split("\n")`/`join` and `surrogateescape` so bytes round-trip.

**A4. Commands** (register all four in `COMMANDS` ~1564)

| Command | Args | Behaviour | Reply |
|---|---|---|---|
| `write-settings` | stdin JSON object, cap `SETTINGS_BYTES` | read existing `spotlight.json` (corrupt JSON → `Denied`, never clobber a hand edit); merge only known keys from the patch; `normalize_settings`; unknown keys already in the file survive; `write_atomic` via `walk([".config","omarchy"], create=True)`. No lock: single writer, QML serializes through one Process. `# ponytail:` comment naming `lock_at` as the upgrade path. | `{"settings": {...}}` |
| `read-binding` | none | scan `bindings.lua` (missing dir/file → nulls): first live `TOGGLE_RE` line → `current`; first `DISABLED_PREFIX` line whose remainder matches → `previous`; `MARK_START` seen → `managed`; plus `_bound_chords()` | `{"current","previous","managed","bound"}` |
| `write-binding <CHORD>` | exactly one arg matching `CHORD_RE` with a `+`, else `Denied("bad chord")` | `own` = chords of our live toggle lines; strip managed block; prefix every live `TOGGLE_RE` line with `DISABLED_PREFIX` (already-disabled lines start with `--` so they never re-match, no double prefix); append `MARK_START`, `hl.unbind("<CHORD>")` only if `chord in bound and chord not in own`, the `o.bind(...)` line, `MARK_END`; `write_atomic(..., _file_mode(...))`. Missing `bindings.lua` is created with the block only. Idempotent: second run yields identical bytes. | `{"chord","unbound","path"}` |
| `revert-binding` | none | strip managed block, strip `DISABLED_PREFIX` from our lines (first restored toggle chord → `restored`), write only if bytes changed | `{"restored": chord|null}` |

Round-trip guarantee: write then revert returns the original bytes exactly. Only exception: a file without a trailing newline gains one. Document, do not fix.

No backup file: the edit is additive and delimited, `revert-binding` is the undo, and the `.bak.<epoch>` files in `~/.config/hypr` come from an agent skill, not Omarchy tooling.

**A5. Tests** (`tests/helper_test.py`, new `class BindingTests` after `HelperTests` ~362; settings cases in `HelperTests`). Fixtures: a `PRINT_FIXTURE` with `SUPER + SPACE → Omarchy menu`, `SUPER SHIFT CTRL + SPACE → Theme menu`, `CTRL + SPACE → Spotlight`, `PRINT → Screenshot`; a `LUA_FIXTURE` with a comment, an unrelated `o.bind`, the hand-written `CTRL + SPACE` Spotlight line, a user-commented `-- o.bind(...)` Spotlight line, and the `Spotlight reminder` line with a `{"query":…}` payload. Mock `HELPER.run_bounded` as the existing tests do (~72-80); temp `HOME` as at ~186-202, factored into a small context manager. Cases:

1. `setupCompleted` default False, `"yes"` clamps to False, True stays True.
2. write-settings creates a 0600 file, ignores unknown patch keys.
3. write-settings preserves unknown file keys, clamps `maxResults` 999 → 50, sets `setupCompleted`.
4. write-settings rejects non-object stdin and a corrupt file, leaves bytes unchanged.
5. `_canon_chord` ordering table.
6. read-binding reports the hand-written chord and the normalized bound map.
7. read-binding tolerates missing hypr dir and missing print tool (`bound == {}`).
8. write-binding accept/deny table (deny `SPACE`, `ALT+SPACE`, `alt + space`, `SHIFT + SUPER + A`, `SUPER + F13`, `SUPER + SPACE; rm -rf`, empty, two args).
9. write-binding disables the old line and appends the block exactly; commented and reminder lines untouched; mode stays 0644.
10. `hl.unbind` only when bound elsewhere: `SUPER + SPACE` yes, `CTRL + SPACE` (own) no.
11. Idempotent, never double-prefixes, also after a print fixture that now lists `ALT + SPACE → Spotlight`.
12. Refuses missing `~/.config/hypr` and an unclosed block.
13. Creates a missing `bindings.lua` with the block only.
14. read-binding after write: `current` new, `previous` old, `managed` true.
15. Write `SUPER + SPACE` then revert → bytes equal `LUA_FIXTURE`, `restored == "CTRL + SPACE"`.
16. Revert without block is a no-op (mtime unchanged); missing file → `restored null`; missing dir → `Denied`.

CI constraint: `git diff --check` runs, so no trailing whitespace in fixtures. CI has no Hyprland tools, so every binding test mocks `run_bounded`.

**A6. Docs**: README "Add a shortcut" section (~29-46) becomes "run the setup tour, or add the line by hand"; uninstall section (~617) mentions the managed block and `revert-binding`.

### Part B: QML (`SetupTour.qml`, `Spotlight.qml`, `lib/Chord.js`, `lib/Commands.js`, `lib/Web.js`)

Two facts that shaped this part: `--print` writes chords as `SUPER SHIFT CTRL + SPACE` while `o.bind()` uses `SUPER + SHIFT + K`, so every chord is canonicalized on the QML side before lookup. And `loadSettings()` (406-424) rebuilds `settings` from an explicit key list, so `setupCompleted` must be added there or it is dropped.

**B1. Component boundary.** `Spotlight.qml` does all I/O (it already owns `helperArgv`, `helperReply`, the Process idiom, teardown). `SetupTour.qml` is pure UI, a `FocusScope` painted as a sibling of `card` inside `panel` so it reuses the PanelWindow, blur namespace, scrim (1694), dismiss `MouseArea` (1708), `HyprlandFocusGrab` and the focus-loss `Connections` (1678-1692). `card` gets `visible: !root.tourActive`; invisible items cannot hold focus, which is what keeps keys away from `input`.

Interface:

```qml
FocusScope {
  // in (bound by Spotlight.qml)
  property color foreground; property color accent; property string fontFamily
  property var settings: ({})
  property string currentBinding: ""     // canonical chord or ""
  property string previousBinding: ""    // disabled hand-written chord or ""
  property bool bindingManaged: false
  property var boundChords: ({})         // canonical chord -> owner text
  property string bindingState: ""       // "" | "busy" | "ok" | "reverted" | "error"
  // owned
  property int step: 0; property bool singleStep: false
  property var draft: ({}); property string selected: ""
  function start(settings, step, single)
  // out
  signal bindingRequested(string chord)
  signal revertRequested()
  signal finished(var patch)   // {} = persist nothing (singleStep); else settings keys (+ setupCompleted)
  signal tryQuery(string text) // emitted right after finished(...)
}
```

Patch semantics: Finish → `draft + {setupCompleted: true}`; Skip or Esc in the full tour → `{setupCompleted: true}`; Done or Esc in singleStep → `{}`; example chip → `finished(draft + completed)` then `tryQuery(text)`. `onBindingStateChanged`: on `ok`/`reverted` clear `selected`, so the primary button falls back to Continue/Done and the status row carries the confirmation.

**B2. Layout.** `ColumnLayout`: `PanelHero` (title, `meta: singleStep ? "" : "Step N of 4"`, glyph `󰍉`) + wrapped subtitle, `PanelSeparator`, `StackLayout { currentIndex: step }` with the four step bodies, `PanelSeparator`, footer `RowLayout` (dots `Repeater { model: 4 }` hidden in singleStep, spacer, "Skip tour", "Back", primary). `StackLayout`'s implicitHeight is the max over all steps, so the surface height is constant across steps for free. Surface: copy `card`'s six glass lines (radius, `Util.alpha(Color.menu.background, 0.62)`, hairline, sheen) plus the click-swallowing `MouseArea` (card 1741). Width `Math.min(Style.space(560), panel.width - Style.space(48))`; height ≈ 520-560 px at base font 12, fits 1080p. `// ponytail: no Flickable; step 3 overflows 1080p only at fontBaseSize > ~18.`

Kit props everywhere: `foreground`, `accent`, `fontFamily` from the tour, `Button` with `focusable: false` (Enter is handled once, by the tour), `bordered: true` on primary and chips, `selected:` on the chosen chip. `Toggle { checked: draft.X; onClicked: set("X", !draft.X) }` where `set()` reassigns `draft = Object.assign({}, draft, {...})` so bindings fire. Sub-toggle `fileSearchAlways` uses `enabled`/`opacity`, never `visible` (keeps StackLayout height fixed). `Dropdown { options: Web.engineOptions() }`. Not used: `TextField` (accepts IME text), `PanelKeyCatcher` (j/k/h/l would fight the recorder).

**B3. Keys.** Tour root, default priority so focused children win: `Escape` → skip/done as above; `Return` → primary; `Left` → back (full tour, step > 0). Esc means "get out" like everywhere in Spotlight; re-entry exists via both actions. Scrim click and focus loss still `dismiss()` without persisting, so a reflexive close brings the tour back next open.

**B4. Recorder + `lib/Chord.js`** (pure JS, numeric Qt constants so `node --test` needs no Qt, export guard like `Web.js` 150-160):

- `fromEvent(key, modifiers)` → `"SUPER + SHIFT + K"` or `""`. Modifier order SUPER (`Qt.Meta` 0x10000000), CTRL (0x04000000), ALT (0x08000000), SHIFT (0x02000000). Keys: A-Z, 0-9, F1-F12, SPACE, RETURN, TAB, BACKSPACE, DELETE, PRINT, arrows. Needs a known key and at least one modifier. `Qt.Key_Enter` (keypad) deliberately unmapped: Hyprland calls it `KP_Enter`.
- `normalize(text)` → canonical form for both spellings (`"SUPER SHIFT CTRL + SPACE"` and `"shift+super+k"`), aliases WIN/LOGO/MOD4 → SUPER, CONTROL → CTRL, MOD1 → ALT. Does not validate the key.
- Recorder item: `BorderSurface` with `Border.controlSpec(activeFocus ? "focus" : "normal", fg, accent)` and `Style.controlFill(...)`, the `TextField.qml` 52-56 recipe without an editable field. `Keys.onPressed`: let Esc, plain Return/Tab/Backtab bubble; otherwise `selected = Chord.fromEvent(...)` when non-empty and `event.accepted = true` (modifier-only presses are swallowed). Focus: `onStepChanged` gives the recorder focus on step 1, else the FocusScope; `start()` does the same via `Qt.callLater` (SpeedTestOverlay 76-83).
- `tests/chord.test.js` (node:test like `web.test.js`): SUPER+SHIFT+K, ALT+SPACE, unmodified SPACE → `""`, Escape → `""`, CTRL+ALT+F6, both `normalize` spellings. Add to `.github/workflows/ci.yml` line 76 if the test files are listed explicitly.

**B5. Step 2 logic** (derived in SetupTour):

```
sameAsCurrent = selected !== "" && selected === currentBinding
owner = selected && selected !== currentBinding && boundChords[selected] !== undefined ? boundChords[selected] : ""
```
- Header: `currentBinding ? "Currently bound to " + currentBinding : "No shortcut yet"`.
- Chips (three `Button`s with a caption under each): caption `Current` / `"Currently: " + boundChords[chord]` / `Recommended` for ALT + SPACE / `""`. On stock Omarchy this yields "Currently: Omarchy menu" under SUPER + SPACE without hardcoding.
- Recorder hint: `sameAsCurrent ? "Already your shortcut" : owner ? "Currently: " + owner + ". It will be unbound." : "If nothing shows up, Hyprland already uses that combination."`
- Primary: label `selected === "" ? (singleStep ? "Done" : "Continue") : owner ? "Replace and set" : "Set shortcut"`; `enabled: !sameAsCurrent && bindingState !== "busy"`; action `selected ? bindingRequested(selected) : (singleStep ? finished({}) : step++)`. With nothing selected, Continue is the keep-current path.
- Status row (fixed height so nothing shifts): text `busy → "Saving..."`, `ok → "Shortcut set to " + currentBinding`, `reverted → currentBinding ? "Restored " + currentBinding : "Managed shortcut removed"`, `error → "Could not write the shortcut. Edit ~/.config/hypr/bindings.lua by hand."`. Button `visible: bindingManaged && previousBinding !== "" && bindingState !== "busy"`, `text: bindingState === "ok" ? "Undo" : "Restore " + previousBinding`, `onClicked: revertRequested()`. One control covers both undo-after-write and restore-on-entry; Spotlight re-runs `read-binding` after every write/revert so the three fields are authoritative.

Steps 1, 3, 4 are static content per the Flow table. Step 4 chips: `firefox`, `f invoice`, `12*1.19`, `5 km in mi`, `remind me tomorrow 9am standup`, `tr hallo welt en`; legend "↵ open · Ctrl+↵ secondary action · Tab complete · Esc clear/close".

**B6. `Spotlight.qml` wiring**

| Where | Edit |
|---|---|
| 14 imports | `import "lib/Chord.js" as Chord` |
| 155-166 literal | `setupCompleted: true` (true = never flash the tour before the helper reply arrives) |
| after 166 | `property bool tourActive: false`, `property string bindingState: ""`, `property var tourBinding: ({ current: "", previous: "", managed: false, bound: {} })` |
| 227 `open()` after `opened = true` | `root.tourActive = false` |
| 252-257 `open()` end | `if (root.settings.setupCompleted === false) root.showTour(0, false)`; `callLater` body becomes `tourActive ? tour.forceActiveFocus() : input.forceActiveFocus()` |
| 406-424 `loadSettings` | add `setupCompleted: parsed.setupCompleted !== false`; after the assignment `if (root.opened && !root.tourActive && root.settings.setupCompleted === false) root.showTour(0, false)` (settings-arrive-after-open race; also the ordinary first-run path) |
| after 358 `toggle()` | `showTour(step, single)`: clear `input.text` and `armedKey`, `bindingState = ""`, `tourActive = true`, `tour.start(settings, step, single)`, `readBinding()`, `Qt.callLater(tour.forceActiveFocus)`. `finishTour(patch)`: `tourActive = false`; if patch has keys, run `write-settings` through `settingsWriteProc` with the same stdin idiom as the existing `write-usage` Process; `Qt.callLater(input.forceActiveFocus)`. `readBinding()` / `writeBinding(chord)` / `revertBinding()`: set `bindingProc.action`, `command = helperArgv([...])`, `running = true` (write/revert set `bindingState = "busy"` first). `loadBinding(reply)`: canonicalize every key of `reply.bound` with `Chord.normalize`, slice owner text to 80 chars, normalize `current`/`previous`, assign `tourBinding` |
| ~1213 activate switch | `case "spotlight-tour": root.showTour(0, false); break` and `case "spotlight-shortcut": root.showTour(1, true); break` (no `dismiss()`) |
| after 1592 `maintenanceProc` | `Process { id: bindingProc; property string action }` with `StdioCollector { waitForEnd: true }`: `read` → `loadBinding(reply)`; write/revert with `!reply` → `bindingState = "error"`; else `Util.execArgv(["hyprctl", "reload"])`, `bindingState = action === "write" ? "ok" : "reverted"`, `readBinding()`. `Process { id: settingsWriteProc }` whose collector calls `root.loadSettings(text)` (the `write-settings` reply has the same `{"settings": ...}` shape as `read-settings`). Separate from `maintenanceProc`: its `if (!reply) return` would swallow the error state, and a settings write must not kill an in-flight binding write |
| 1603-1614 `Component.onDestruction` | stop `bindingProc` and `settingsWriteProc` |
| 1713 `card` | `visible: !root.tourActive` |
| after 2095 | `SetupTour { id: tour; visible: root.tourActive; anchors.centerIn: parent; ... }` binding the inputs above, `onBindingRequested → root.writeBinding`, `onRevertRequested → root.revertBinding`, `onFinished → root.finishTour`, `onTryQuery → input.text = text; input.cursorPosition = text.length` |

**B7. `lib/Commands.js`** after line 15, same shape as the existing rows:
- `spotlight.tour`: title "Run Setup Tour", subtitle "Shortcut, search sources and a quick try-out", icon `󰋗`, `kind: "spotlight-tour"`, keywords `spotlight setup tour welcome onboarding first run help`.
- `spotlight.shortcut`: title "Change Spotlight Shortcut", subtitle "Set, change or restore the key that opens Spotlight", icon `󰌌`, `kind: "spotlight-shortcut"`, keywords `spotlight shortcut keybinding hotkey bind key rebind restore`.

**B8. `lib/Web.js`** after `lookupEngine` (~47): `engineOptions()` → `[{value, label}]` deduped by engine name keeping the first key (`g` wins over `google`), added to the export guard; one assertion in `tests/web.test.js`.

## Verification

Automated (all from the plugin root):

```
python -m unittest -v tests/helper_test.py
node --test tests/*.test.js
node --check lib/Chord.js lib/Commands.js lib/Web.js
python3 -m py_compile bin/spotlight-helper
/usr/lib/qt6/bin/qmlformat -n Spotlight.qml > /dev/null
/usr/lib/qt6/bin/qmlformat -n SetupTour.qml > /dev/null
git diff --check
```
`qmllint` segfaults on Spotlight.qml, skip it. CI has no Hyprland tools, so every binding test mocks `run_bounded`.

Helper round-trip against a copy of the real file (`HOME` pointed at a scratch dir containing a copy of `~/.config/hypr/bindings.lua`): `read-binding` reports `CTRL + SPACE`; `write-binding "ALT + SPACE"` disables line 34 and appends the block; `read-binding` shows current/previous/managed; `revert-binding` restores byte-identical content (`cmp`).

Live shell: finish all edits first (the plugin-dir watcher tears the overlay down on any save), then `omarchy restart shell` (`rescanPlugins` does not replace a keepLoaded instance). Force the tour with `printf '{"setupCompleted":false}' | python3 bin/spotlight-helper write-settings` and open Spotlight, or open Spotlight and run "Run Setup Tour".

Manual script (user does screenshots, I do the same run first):
1. Tour appears instead of the search card; typing does nothing to the hidden input.
2. Esc closes it; `spotlight.json` shows `"setupCompleted": true`; force false again.
3. Step 2 on this machine: header "Currently bound to CTRL + SPACE"; chips show "Recommended" under ALT + SPACE and "Currently: Omarchy menu" under SUPER + SPACE. Record SUPER + SHIFT + K → shown. Record CTRL + SPACE → "Already your shortcut", button disabled. Pick ALT + SPACE → "Set shortcut" → "Shortcut set to ALT + SPACE" + Undo; `hyprctl binds | grep -i spotlight` confirms; ALT + SPACE opens Spotlight. Undo → "Restored CTRL + SPACE"; `bindings.lua` byte-identical to before.
4. Step 3: toggle Web suggestions on, pick DuckDuckGo, Finish → `spotlight.json` reflects both.
5. Reopen, type `shortcut`, Enter → single-step card: no dots, no Back, no Skip, "Done"; Done writes nothing.
6. Step 4 chip `12*1.19` → tour closes, the `14.28` row is visible in the real results.
7. Error path: `chmod 500 ~/.config/hypr` temporarily, set a shortcut → error status text, no crash; restore mode.

Screenshots (`omarchy capture screenshot fullscreen`): one per step, step 2 in three states (conflict chip selected, after write with Undo, error), single-step mode.

## Unverified assumptions (confirm live, first thing after implementation)

- `Qt.MetaModifier` is Super under Quickshell/Wayland (record SUPER + SHIFT + K).
- `hl.unbind("SUPER + SPACE")` in `bindings.lua` removes Omarchy's default menu bind on `hyprctl reload` (the `own` rule keeps us from ever unbinding our own chord).
- Hyprland accepts uppercase key names (`SPACE`, `F6`, `LEFT`); observed in Omarchy's own configs, not checked in source.
