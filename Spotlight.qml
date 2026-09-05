import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "lib/Calc.js" as Calc
import "lib/Units.js" as Units
import "lib/NaturalTime.js" as NaturalTime
import "lib/Web.js" as Web
import "lib/Fuzzy.js" as Fuzzy
import "lib/Frecency.js" as Frecency
import "lib/Commands.js" as Commands

// Spotlight — a Raycast-shaped command palette for Omarchy.
//
// One overlay, many providers. Each provider turns the query into rows; the
// rows are plain data carrying a `kind`, and activate() is the only place that
// turns a kind into an effect. Nothing from the query is ever evaluated: the
// calculator has its own parser and every command runs through an argv vector.
Item {
  id: root

  // ------------------------------------------------------------- injected
  property string omarchyPath: Quickshell.env("OMARCHY_PATH")
  property var shell: null
  property var manifest: null

  readonly property string pluginId: (manifest && manifest.id) || "majix.spotlight"
  readonly property var appLibrary: root.shell ? root.shell.appLibrary : null
  readonly property string home: Quickshell.env("HOME")

  // ------------------------------------------------------------- state
  property bool opened: false
  property string query: ""
  property int selectedIndex: 0
  property bool cursorActive: true

  // Rows currently on screen, as plain JS objects. displayModel mirrors only
  // the display fields; the payload stays here and is read back by index, so
  // ListModel never has to hold a nested object.
  property var rows: []

  // Async provider caches. Each is refreshed by its own Process and triggers a
  // rebuild when it lands, so a slow provider never blocks the fast ones.
  property var suggestionRows: []
  property string suggestionFor: ""
  property var fileRows: []
  property string fileFor: ""
  property var reminderRows: []
  property var clipboardRows: []

  // Destructive commands need a second Enter. Holds the row key that is armed.
  property string armedKey: ""

  // The row the user deliberately put the cursor on — arrow keys, or a pointer
  // that actually moved. Empty means "whatever is top right now", and that is
  // the rule that makes Enter safe while async rows are still landing: a late
  // rebuild can reshuffle the list without the cursor ever drifting off the
  // best answer onto a web suggestion.
  property string pinnedKey: ""

  // Decayed launch counts, keyed by row key. See lib/Frecency.js.
  property var usage: ({})

  // Frecency is a bonus on top of the match score, never a replacement for it.
  // Both caps sit under the smallest gap between two match tiers (500 in the
  // shell's AppSearch, 500 in Fuzzy), so usage reorders rows that matched
  // equally well and can never lift a weak match over a name that starts with
  // what was typed.
  readonly property int appFrecencyBoost: 450
  readonly property int commandFrecencyBoost: 400
  // With no query there is no match score to respect, so frecency owns the
  // order outright and the alphabetical fallback only breaks its ties.
  readonly property int idleFrecencyBoost: 100000
  // Cap on remembered keys. Everything past it is the tail nothing ranks by.
  readonly property int usageKeepCount: 400

  property var settings: ({
    webSuggestions: true,
    searchEngine: "g",
    fileSearch: true,
    maxApps: 8,
    maxSuggestions: 4
  })

  // ------------------------------------------------------------- theme
  // Shares the [menu] surface tokens, so any theme that styles the Omarchy
  // menu styles this too. The card is deliberately translucent: the frost is
  // Hyprland's, applied to this layer's namespace.
  readonly property color foreground: Color.menu.text
  readonly property color accent: Color.accent
  // Frosted glass needs something left to frost: at 0.86 the card is opaque
  // and Hyprland's blur has no visible effect. 0.62 keeps text contrast while
  // letting the blurred wallpaper through as colour and shape.
  readonly property color glassBackground: Util.alpha(Color.menu.background, 0.62)
  readonly property color glassBorder: Util.alpha(Color.foreground, 0.16)
  readonly property color glassSheen: Util.alpha("#ffffff", 0.07)
  readonly property color scrim: Util.alpha(Color.menu.scrim, 0.25)
  readonly property color selectedBackground: Util.alpha(Color.foreground, 0.12)
  readonly property color selectedText: Color.menu.selectedText
  readonly property color dividerColor: Util.alpha(Color.foreground, 0.10)
  readonly property string fontFamily: Style.font.menuFamily

  // One left rail at `gutter`. The search glyph, every row icon and every
  // section header align to it; a row is inset by `listPadding` and carries
  // the remainder internally, so the rail survives the inset.
  readonly property int gutter: Style.space(24)
  readonly property int listPadding: Style.space(10)
  readonly property int rowInset: gutter - listPadding

  readonly property int cardRadius: Style.space(12)
  readonly property int rowRadius: Style.space(8)
  readonly property int searchHeight: Style.space(56)
  readonly property int rowHeight: Style.space(40)
  readonly property int sectionHeight: Style.space(30)
  readonly property int footerHeight: Style.space(36)
  readonly property int maxListHeight: Style.space(400)
  readonly property int hairline: Style.spacing.hairline

  // Between heading (16) and display (24): a hero input that is still an
  // input. Scales with the user's font size rather than being pinned to 18px.
  readonly property int searchFontSize: Math.round(Style.font.baseSize * 1.5)

  // Fixing the top edge at the position the *fully expanded* panel would need
  // to sit centred means the panel grows downward into the middle of the
  // screen instead of shoving the search field around as results arrive.
  readonly property int maxCardHeight: searchHeight + hairline
    + listPadding * 2 + maxListHeight + hairline + footerHeight

  // ------------------------------------------------------------- lifecycle
  // The payload may carry {"query": "..."} so a keybind can summon Spotlight
  // already primed, e.g. bound to open straight into "remind me ".
  function open(payloadJson) {
    var initial = ""
    try {
      var payload = JSON.parse(String(payloadJson || "{}"))
      if (payload && typeof payload.query === "string") initial = payload.query
    } catch (e) {
      initial = ""
    }

    root.opened = true
    root.armedKey = ""
    root.rows = []
    root.pinnedKey = ""
    input.text = initial
    input.cursorPosition = initial.length
    root.selectedIndex = 0
    root.cursorActive = true
    root.suggestionRows = []
    root.suggestionFor = ""
    root.fileRows = []
    root.fileFor = ""
    // The panel appears under wherever the pointer already is. Hold the cursor
    // for the same beat a keystroke would, so opening over a row does not hand
    // it the selection before the first character is typed.
    typingGuard.restart()
    if (root.appLibrary) root.appLibrary.refreshIcons()
    remindersProbe.running = true
    root.rebuild()
    pointerGate.reset()
    Qt.callLater(function() {
      input.forceActiveFocus()
      resultList.positionViewAtBeginning()
    })
  }

  function close() {
    root.opened = false
    root.armedKey = ""
    suggestDebounce.stop()
    fileDebounce.stop()
  }

  // Escape and successful activations go through here so the shell's
  // openPanelIds stays in step — otherwise the next toggle would try to hide
  // an overlay that is already gone.
  function dismiss() {
    root.opened = false
    root.armedKey = ""
    if (root.shell && typeof root.shell.hide === "function") root.shell.hide(root.pluginId)
  }

  function toggle() {
    if (root.opened) root.dismiss()
    else root.open("{}")
  }

  // ------------------------------------------------------------- usage
  // Only keys that still mean the same thing next week are worth remembering.
  // A web suggestion, a file hit or a window is spelled out of the query that
  // produced it and is never looked up again, so counting one only grows the
  // file.
  function trackable(key) {
    var k = String(key || "")
    return k.indexOf("app:") === 0 || k.indexOf("cmd:") === 0 || k.indexOf("bang.") === 0
  }

  function bumpUsage(key) {
    if (!root.trackable(key)) return
    var now = Date.now()
    var next = Frecency.prune(Frecency.bump(root.usage, key, now), root.usageKeepCount, now)
    root.usage = next
    usageFile.setText(JSON.stringify(next))
  }

  function loadUsage(raw) {
    try {
      var parsed = JSON.parse(String(raw || "{}"))
      root.usage = (parsed && typeof parsed === "object") ? parsed : ({})
    } catch (e) {
      root.usage = ({})
    }
  }

  function loadSettings(raw) {
    var next = {
      webSuggestions: true,
      searchEngine: "g",
      fileSearch: true,
      maxApps: 8,
      maxSuggestions: 4
    }
    try {
      var parsed = JSON.parse(String(raw || "{}"))
      for (var k in next) if (parsed[k] !== undefined) next[k] = parsed[k]
    } catch (e) {
      // Malformed settings fall back to the defaults rather than breaking the
      // launcher; printErrors stays off so a missing file is silent.
    }
    root.settings = next
  }

  // ------------------------------------------------------------- providers
  function row(spec) {
    return {
      key: spec.key || "",
      section: spec.section || "",
      kind: spec.kind || "noop",
      title: String(spec.title || ""),
      subtitle: String(spec.subtitle || ""),
      accessory: String(spec.accessory || ""),
      icon: String(spec.icon || ""),
      image: String(spec.image || ""),
      mono: spec.mono === true,
      primaryLabel: spec.primaryLabel || "Open",
      secondaryLabel: spec.secondaryLabel || "",
      confirm: spec.confirm === true,
      payload: spec.payload || ({})
    }
  }

  // Calculator, unit conversion, reminders, calendar, URLs and bangs. These
  // are the rows that answer the query directly, so they sort above search.
  function intentRows(q) {
    var out = []

    var calc = Calc.evaluate(q)
    if (calc) {
      out.push(root.row({
        key: "calc", section: "Calculator", kind: "copy",
        title: calc.text, subtitle: q.replace(/^=/, "").trim(),
        accessory: "Copy", icon: "󰃬", mono: true,
        primaryLabel: "Copy result",
        payload: { text: calc.text.replace(/\s/g, "") }
      }))
    }

    var unit = Units.convert(q)
    if (unit) {
      out.push(root.row({
        key: "unit", section: "Conversion", kind: "copy",
        title: unit.text, subtitle: unit.detail,
        accessory: unit.family, icon: "󰑤", mono: true,
        primaryLabel: "Copy result",
        payload: { text: unit.text.replace(/\s/g, "") }
      }))
    }

    var reminder = NaturalTime.parseReminder(q)
    if (reminder && !reminder.needsTime && reminder.message) {
      out.push(root.row({
        key: "reminder.create", section: "Reminder", kind: "reminder",
        title: reminder.message,
        subtitle: "Notify " + reminder.label + " · in " + NaturalTime.formatDuration(reminder.minutes),
        accessory: "Reminder", icon: "󰢌",
        primaryLabel: "Set reminder",
        payload: { minutes: reminder.minutes, message: reminder.message }
      }))
    } else if (reminder && reminder.needsTime) {
      out.push(root.row({
        key: "reminder.hint", section: "Reminder", kind: "noop",
        title: reminder.message || "Set a reminder",
        subtitle: "Add a time — “in 20m”, “at 15:30”, “tomorrow at 9”",
        accessory: "Needs a time", icon: "󰢌",
        primaryLabel: ""
      }))
    }

    var event = NaturalTime.parseEvent(q)
    if (event) {
      out.push(root.row({
        key: "event.create", section: "Calendar", kind: "event",
        title: event.title,
        subtitle: event.label + " · " + NaturalTime.formatDuration(event.durationMinutes),
        accessory: "Google Calendar", icon: "󰸗",
        primaryLabel: "Add to Google Calendar",
        secondaryLabel: "Save .ics file",
        payload: {
          title: event.title,
          start: NaturalTime.toUtcBasic(event.start),
          end: NaturalTime.toUtcBasic(event.end)
        }
      }))
    }

    var url = Web.detectUrl(q)
    if (url) {
      out.push(root.row({
        key: "url.open", section: "Open", kind: "url",
        title: url.replace(/^https?:\/\//, ""), subtitle: url,
        accessory: "Website", icon: "󰖟",
        primaryLabel: "Open in browser",
        payload: { url: url }
      }))
    }

    return out
  }

  // A bare bang is a prefix, not a sigil — "gh quickshell" is a GitHub search.
  // That makes it a trap for any application whose name starts with an engine
  // key and carries a space, "docker desktop" being the obvious one, so the
  // bang row is built here and pushed below the applications rather than
  // taking the cursor off them.
  function bangRows(q) {
    var bang = Web.bang(q)
    if (!bang) return []
    return [root.row({
      key: "bang." + bang.key, section: "Search", kind: "url",
      title: bang.query, subtitle: "Search " + bang.engine.name,
      accessory: bang.engine.name, icon: bang.engine.icon,
      primaryLabel: "Search " + bang.engine.name,
      payload: { url: Web.searchUrl(bang.query, bang.key) }
    })]
  }

  function appRows(q) {
    if (!root.appLibrary) return []
    var entries = root.appLibrary.sortedEntries(q)
    var now = Date.now()
    var candidates = []
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i].entry
      var key = "app:" + String(entry.id || "")
      // sortedEntries scored the match as well as ordering it, and keeping
      // that number instead of the position is what lets frecency stay a
      // bounded bonus. Flattened to a rank position, "the name starts with the
      // query" and "one letter of the acronym matched" sit a single point
      // apart, so any usage at all was enough to swap them.
      candidates.push({
        key: key,
        entry: entry,
        order: i,
        score: (q ? (Number(entries[i].score) || 0) : 0)
          + Frecency.weight(root.usage[key], now) * (q ? root.appFrecencyBoost : root.idleFrecencyBoost)
      })
    }
    candidates.sort(function(a, b) {
      if (b.score !== a.score) return b.score - a.score
      return a.order - b.order
    })

    var limit = q ? Math.max(3, Number(root.settings.maxApps) || 8) : 60
    var out = []
    for (var j = 0; j < candidates.length && out.length < limit; j++) {
      var c = candidates[j]
      out.push(root.row({
        key: c.key,
        section: "Applications", kind: "app",
        title: root.appLibrary.entryName(c.entry),
        subtitle: root.appLibrary.entrySubtext(c.entry),
        accessory: "Application",
        image: root.appLibrary.iconSource(c.entry.icon),
        primaryLabel: "Open",
        payload: { appId: String(c.entry.id || ""), name: root.appLibrary.entryName(c.entry) }
      }))
    }
    return out
  }

  // Open windows, so "switch to that Slack window" is one query away.
  function windowRows(q) {
    if (!q) return []
    var candidates = []
    var values = []
    try { values = ToplevelManager.toplevels.values || [] } catch (e) { return [] }

    for (var i = 0; i < values.length; i++) {
      var t = values[i]
      if (!t) continue
      var title = String(t.title || "")
      var appId = String(t.appId || "")
      if (!title && !appId) continue
      candidates.push({
        title: title || appId,
        subtitle: appId,
        keywords: "window switch focus " + appId,
        toplevel: t
      })
    }

    var ranked = Fuzzy.rank(candidates, q, 5)
    var out = []
    for (var j = 0; j < ranked.length; j++) {
      out.push(root.row({
        key: "win:" + ranked[j].subtitle + ":" + ranked[j].title,
        section: "Open Windows", kind: "window",
        title: ranked[j].title, subtitle: ranked[j].subtitle,
        accessory: "Window", icon: "󰖯",
        primaryLabel: "Focus window",
        secondaryLabel: "Close window",
        payload: { toplevel: ranked[j].toplevel }
      }))
    }
    return out
  }

  function commandRows(q) {
    if (!q) return []
    var catalogue = Commands.commands().concat(Commands.quicklinks())
    var ranked = Fuzzy.rank(catalogue, q, 40)

    // Usage reorders within the matched set without overriding a strong
    // title match, hence the bonus being added to the fuzzy score.
    var now = Date.now()
    var scored = []
    for (var i = 0; i < ranked.length; i++) {
      var key = "cmd:" + ranked[i].key
      scored.push({
        cmd: ranked[i],
        score: Fuzzy.score(ranked[i], q) + Frecency.weight(root.usage[key], now) * root.commandFrecencyBoost,
        order: i
      })
    }
    scored.sort(function(a, b) {
      if (b.score !== a.score) return b.score - a.score
      return a.order - b.order
    })

    var out = []
    for (var j = 0; j < scored.length && j < 7; j++) {
      var c = scored[j].cmd
      out.push(root.row({
        key: "cmd:" + c.key,
        section: c.kind === "url" ? "Quicklinks" : "Commands",
        kind: c.kind,
        title: c.title, subtitle: c.subtitle,
        accessory: c.kind === "url" ? "Link" : "Command",
        icon: c.icon,
        primaryLabel: c.kind === "url" ? "Open in browser" : "Run",
        confirm: c.confirm === true,
        payload: { cmd: c.cmd || "", id: c.id || "", url: c.url || "" }
      }))
    }
    return out
  }

  function clipboardQuery(q) {
    var m = String(q || "").match(/^(?:cb|clip|clipboard)\s+(\S.*)$/i)
    return m ? m[1].trim() : ""
  }

  function clipboardResultRows(q) {
    var needle = root.clipboardQuery(q)
    if (!needle) return []
    var ranked = Fuzzy.rank(root.clipboardRows, needle, 8)
    var out = []
    for (var i = 0; i < ranked.length; i++) {
      out.push(root.row({
        key: "clip:" + i,
        section: "Clipboard History", kind: "copy",
        title: ranked[i].title, subtitle: "",
        accessory: "Copy", icon: "󰅌", mono: true,
        primaryLabel: "Copy to clipboard",
        payload: { text: ranked[i].fullText }
      }))
    }
    return out
  }

  function reminderListRows(q) {
    if (!/^reminders?$/i.test(String(q || "").trim())) return []
    if (root.reminderRows.length === 0) {
      return [root.row({
        key: "reminder.none", section: "Reminders", kind: "noop",
        title: "No active reminders", subtitle: "Try “remind me in 20m to …”",
        accessory: "", icon: "󰢌", primaryLabel: ""
      })]
    }
    var out = []
    for (var i = 0; i < root.reminderRows.length; i++) {
      var r = root.reminderRows[i]
      out.push(root.row({
        key: "reminder.active." + i,
        section: "Reminders", kind: "noop",
        title: String(r.label || ""),
        subtitle: "in " + String(r.remaining || "") + " · at " + String(r.atTime || ""),
        accessory: "Active", icon: "󰔟", primaryLabel: ""
      }))
    }
    out.push(root.row({
      key: "reminder.clear", section: "Reminders", kind: "shell",
      title: "Clear all reminders", subtitle: root.reminderRows.length + " active",
      accessory: "Command", icon: "󰩹",
      primaryLabel: "Clear", payload: { cmd: "omarchy reminder clear" }
    }))
    return out
  }

  function fileResultRows(q) {
    if (root.fileRows.length === 0) return []
    var out = []
    for (var i = 0; i < root.fileRows.length && i < 10; i++) {
      var f = root.fileRows[i]
      out.push(root.row({
        key: "file:" + f.path,
        section: "Files", kind: "file",
        title: f.name, subtitle: f.dir,
        accessory: f.isDir ? "Folder" : "File",
        icon: f.isDir ? "󰉋" : "󰈔",
        primaryLabel: "Open",
        secondaryLabel: "Open folder",
        payload: { path: f.path, dir: f.dir }
      }))
    }
    return out
  }

  function suggestionResultRows(q) {
    if (root.suggestionRows.length === 0) return []
    var engine = String(root.settings.searchEngine || "g")
    var out = []
    for (var i = 0; i < root.suggestionRows.length; i++) {
      var s = root.suggestionRows[i]
      out.push(root.row({
        key: "sugg:" + s,
        section: "Web Suggestions", kind: "url",
        title: s, subtitle: "",
        accessory: Web.engineName(engine),
        icon: Web.engineIcon(engine),
        primaryLabel: "Search " + Web.engineName(engine),
        payload: { url: Web.searchUrl(s, engine) }
      }))
    }
    return out
  }

  function webFallbackRows(q) {
    if (!q) return []
    if (Web.detectUrl(q)) return []
    var engine = String(root.settings.searchEngine || "g")
    return [root.row({
      key: "web.fallback", section: "Search the Web", kind: "url",
      title: "Search " + Web.engineName(engine) + " for “" + q + "”",
      subtitle: "",
      accessory: Web.engineName(engine),
      icon: Web.engineIcon(engine),
      primaryLabel: "Search " + Web.engineName(engine),
      payload: { url: Web.searchUrl(q, engine) }
    })]
  }

  // ------------------------------------------------------------- assembly
  function rebuild() {
    var q = String(root.query || "").trim()

    var next = []
    function push(list) { for (var i = 0; i < list.length; i++) next.push(list[i]) }

    push(root.intentRows(q))
    push(root.clipboardResultRows(q))
    push(root.reminderListRows(q))
    push(root.appRows(q))
    push(root.windowRows(q))
    push(root.bangRows(q))
    push(root.commandRows(q))
    push(root.fileResultRows(q))
    push(root.suggestionResultRows(q))
    push(root.webFallbackRows(q))

    root.rows = next

    displayModel.clear()
    for (var j = 0; j < next.length; j++) {
      var r = next[j]
      displayModel.append({
        rowIndex: j,
        section: r.section,
        rowTitle: r.title,
        rowSubtitle: r.subtitle,
        rowAccessory: r.accessory,
        rowIcon: r.icon,
        rowImage: r.image,
        rowMono: r.mono,
        selectable: r.kind !== "noop"
      })
    }

    // A deliberate cursor is restored by key, so an async refresh cannot move
    // it. Everything else follows the top row on every single rebuild: a key
    // that outlives the query it was built for — the web-search fallback, a
    // suggestion still on screen while its replacement is in flight — must
    // never inherit the cursor and turn the next Enter into a web search.
    var restored = root.pinnedKey ? root.indexOfKey(root.pinnedKey) : -1
    if (root.pinnedKey && restored < 0) root.pinnedKey = ""
    root.selectedIndex = restored >= 0 ? restored : root.firstSelectableIndex()
    root.cursorActive = next.length > 0
    pointerGate.reset()
    Qt.callLater(function() {
      if (displayModel.count > 0) resultList.positionViewAtIndex(root.selectedIndex, ListView.Contain)
    })
  }

  function selectedRowKey() {
    var r = root.rows[root.selectedIndex]
    return r ? r.key : ""
  }

  function indexOfKey(key) {
    for (var i = 0; i < root.rows.length; i++) if (root.rows[i].key === key) return i
    return -1
  }

  function firstSelectableIndex() {
    for (var i = 0; i < root.rows.length; i++) if (root.rows[i].kind !== "noop") return i
    return 0
  }

  function selectedRow() {
    return root.rows[root.selectedIndex] || null
  }

  // Only a pointer that actually moved may move the cursor, and not while the
  // keyboard is still mid-thought. The card animates its height as rows
  // arrive, so a pointer resting anywhere over the list has rows sliding under
  // it on every keystroke; hover winning that race is how "stea" ends up
  // selecting a web suggestion instead of Steam.
  function selectFromPointer(index, item, mouse) {
    if (typingGuard.running) return
    if (!root.rows[index] || root.rows[index].kind === "noop") return
    if (!pointerGate.moved(item, mouse)) return
    root.cursorActive = true
    root.selectedIndex = index
    root.pinnedKey = root.selectedRowKey()
    root.armedKey = ""
  }

  // Steps over "noop" rows (hints, reminder listings) so the cursor only ever
  // rests somewhere Enter means something.
  function select(delta) {
    var count = root.rows.length
    if (count === 0) return
    var index = root.selectedIndex
    for (var step = 0; step < count; step++) {
      index = (index + delta + count) % count
      if (root.rows[index] && root.rows[index].kind !== "noop") break
    }
    root.selectedIndex = index
    root.pinnedKey = root.selectedRowKey()
    root.cursorActive = true
    root.armedKey = ""
    pointerGate.reset()
    resultList.positionViewAtIndex(index, ListView.Contain)
  }

  function selectPage(delta) {
    var count = root.rows.length
    if (count === 0) return
    var visible = Math.max(1, Math.floor(resultList.height / root.rowHeight))
    var index = Math.max(0, Math.min(count - 1, root.selectedIndex + delta * visible))
    while (index >= 0 && index < count && root.rows[index] && root.rows[index].kind === "noop")
      index += delta > 0 ? 1 : -1
    if (index < 0 || index >= count) index = delta > 0 ? count - 1 : 0
    root.selectedIndex = index
    root.pinnedKey = root.selectedRowKey()
    root.cursorActive = true
    root.armedKey = ""
    pointerGate.reset()
    resultList.positionViewAtIndex(index, ListView.Contain)
  }

  // ------------------------------------------------------------- actions
  function openUrl(url) {
    if (!url) return
    Util.execArgv(["omarchy-launch-browser", String(url)])
  }

  // Enter comes through here rather than going straight at selectedIndex.
  // With no deliberate cursor the intent is always "the best row for what I
  // typed", and resolving that at the keystroke closes the window between a
  // rebuild landing and the cursor settling onto it.
  function activateSelection(secondary) {
    root.activate(root.pinnedKey ? root.selectedIndex : root.firstSelectableIndex(), secondary)
  }

  function activate(index, secondary) {
    var r = root.rows[index]
    if (!r || r.kind === "noop") return

    // One confirmation for the rows that end the session.
    if (r.confirm && !secondary && root.armedKey !== r.key) {
      root.armedKey = r.key
      return
    }
    root.armedKey = ""

    switch (r.kind) {
    case "app":
      root.bumpUsage(r.key)
      root.dismiss()
      if (root.appLibrary) root.appLibrary.launch(r.payload.appId, r.payload.name)
      break

    case "shell":
      root.bumpUsage(r.key)
      root.dismiss()
      Util.execDetached(r.payload.cmd)
      break

    case "url":
      root.bumpUsage(r.key)
      root.dismiss()
      root.openUrl(r.payload.url)
      break

    case "summon":
      root.bumpUsage(r.key)
      root.dismiss()
      if (root.shell && typeof root.shell.summon === "function")
        root.shell.summon(r.payload.id, "{}")
      break

    case "copy":
      root.dismiss()
      // wl-copy over argv, never a shell string: the text is user data.
      Util.execArgv(["wl-copy", "--", String(r.payload.text || "")])
      break

    case "reminder":
      root.dismiss()
      Util.execArgv(["omarchy-reminder", String(r.payload.minutes), String(r.payload.message || "")])
      break

    case "event":
      root.dismiss()
      if (secondary) root.saveIcs(r.payload)
      else root.openUrl("https://calendar.google.com/calendar/render?action=TEMPLATE"
        + "&text=" + encodeURIComponent(r.payload.title)
        + "&dates=" + r.payload.start + "/" + r.payload.end)
      break

    case "window":
      root.dismiss()
      try {
        if (secondary) r.payload.toplevel.close()
        else r.payload.toplevel.activate()
      } catch (e) {
        console.warn("spotlight: window action failed:", e)
      }
      break

    case "file":
      root.dismiss()
      if (secondary) Util.execArgv(["xdg-open", String(r.payload.dir || "")])
      else Util.execArgv(["xdg-open", String(r.payload.path || "")])
      break
    }
  }

  // Writes the event as an .ics next to the user's downloads and hands it to
  // the desktop. The payload goes in as positional args so a title with
  // quotes in it cannot break out of the command.
  function saveIcs(payload) {
    var stamp = payload.start.replace(/[^0-9TZ]/g, "")
    var path = root.home + "/Downloads/omarchy-event-" + stamp + ".ics"
    var ics = [
      "BEGIN:VCALENDAR",
      "VERSION:2.0",
      "PRODID:-//Omarchy//Spotlight//EN",
      "CALSCALE:GREGORIAN",
      "METHOD:PUBLISH",
      "BEGIN:VEVENT",
      "UID:spotlight-" + stamp + "@omarchy",
      "DTSTAMP:" + payload.start,
      "DTSTART:" + payload.start,
      "DTEND:" + payload.end,
      "SUMMARY:" + String(payload.title).replace(/([,;\\])/g, "\\$1"),
      "END:VEVENT",
      "END:VCALENDAR",
      ""
    ].join("\r\n")

    Quickshell.execDetached([
      "bash", "-lc",
      'mkdir -p "$(dirname "$2")" && printf %s "$1" > "$2" && exec xdg-open "$2"',
      "bash", ics, path
    ])
  }

  // ------------------------------------------------------------- async data
  function loadSuggestions(raw, forQuery) {
    if (forQuery !== String(root.query || "").trim()) return
    root.suggestionRows = Web.parseSuggestions(raw, forQuery, Math.max(0, Number(root.settings.maxSuggestions) || 4))
    root.suggestionFor = forQuery
    root.rebuild()
  }

  function fileSearchTarget(q) {
    var s = String(q || "").trim()
    var m = s.match(/^(?:f|file|files)\s+(\S.*)$/i)
    if (m) return { pattern: m[1].trim(), dir: root.home }
    if (/^~\//.test(s) || /^\//.test(s)) {
      var slash = s.lastIndexOf("/")
      var dir = s.slice(0, slash + 1).replace(/^~/, root.home)
      var pattern = s.slice(slash + 1)
      return { pattern: pattern || ".", dir: dir }
    }
    return null
  }

  function loadFiles(raw, forQuery) {
    if (forQuery !== String(root.query || "").trim()) return
    var lines = String(raw || "").split("\n")
    var out = []
    for (var i = 0; i < lines.length; i++) {
      var path = lines[i].replace(/\/$/, "")
      if (!path) continue
      var isDir = lines[i].slice(-1) === "/"
      var slash = path.lastIndexOf("/")
      out.push({
        path: path,
        name: slash >= 0 ? path.slice(slash + 1) : path,
        dir: slash > 0 ? path.slice(0, slash) : "/",
        isDir: isDir
      })
    }
    root.fileRows = out
    root.fileFor = forQuery
    root.rebuild()
  }

  function loadReminders(raw) {
    try {
      var parsed = JSON.parse(String(raw || "{}"))
      root.reminderRows = Array.isArray(parsed.reminders) ? parsed.reminders : []
    } catch (e) {
      root.reminderRows = []
    }
    if (root.opened) root.rebuild()
  }

  function loadClipboard(raw) {
    var out = []
    try {
      var parsed = JSON.parse(String(raw || "[]"))
      for (var i = 0; i < parsed.length && i < 200; i++) {
        var item = parsed[i]
        if (!item || item.type !== "text") continue
        var text = String(item.text || "")
        var flat = text.replace(/\s+/g, " ").trim()
        if (!flat) continue
        out.push({ title: flat.length > 120 ? flat.slice(0, 120) + "…" : flat, fullText: text })
      }
    } catch (e) {
      out = []
    }
    root.clipboardRows = out
  }

  // Query changes fan out to the async providers on a short debounce so a
  // fast typist does not spawn a process per keystroke.
  onQueryChanged: {
    root.armedKey = ""
    // A new query invalidates a deliberate cursor: the row it named may not
    // even be in the list any more.
    root.pinnedKey = ""
    typingGuard.restart()

    var q = String(root.query || "").trim()

    var target = root.settings.fileSearch ? root.fileSearchTarget(q) : null
    if (target && target.pattern.length >= 1) {
      fileDebounce.pattern = target.pattern
      fileDebounce.dir = target.dir
      fileDebounce.forQuery = q
      fileDebounce.restart()
    } else {
      fileDebounce.stop()
      if (root.fileRows.length > 0) { root.fileRows = []; root.fileFor = "" }
    }

    var wantSuggestions = root.settings.webSuggestions && q.length >= 2
      && !Web.detectUrl(q) && !Web.bang(q) && !Calc.evaluate(q)
      && !NaturalTime.isReminderQuery(q) && !NaturalTime.isEventQuery(q)
      && !root.clipboardQuery(q) && !root.fileSearchTarget(q)
    if (wantSuggestions) {
      suggestDebounce.forQuery = q
      suggestDebounce.restart()
      // Suggestions go stale the moment the query stops being a continuation
      // of the one that fetched them. Keeping the ones the new query still
      // narrows is what stops the list collapsing on every keystroke; dropping
      // the rest is what stops "stea" offering what "ste" asked for.
      if (root.suggestionFor && q.indexOf(root.suggestionFor) !== 0) {
        root.suggestionRows = []
        root.suggestionFor = ""
      }
    } else {
      suggestDebounce.stop()
      if (root.suggestionRows.length > 0) { root.suggestionRows = []; root.suggestionFor = "" }
    }

    // Last, so the rows show the caches this pass just invalidated rather than
    // the ones it is about to.
    root.rebuild()
  }

  // A keystroke owns the cursor for a moment afterwards: long enough to cover
  // the card's height animation and the hover events it generates as rows
  // slide under a stationary pointer, short enough that reaching for the mouse
  // straight after typing still works.
  Timer {
    id: typingGuard
    interval: 400
  }

  Timer {
    id: suggestDebounce
    interval: 220
    property string forQuery: ""
    onTriggered: {
      if (suggestProc.running) suggestProc.running = false
      suggestProc.forQuery = suggestDebounce.forQuery
      suggestProc.command = Web.suggestArgv(suggestDebounce.forQuery)
      suggestProc.running = true
    }
  }

  Process {
    id: suggestProc
    property string forQuery: ""
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.loadSuggestions(text, suggestProc.forQuery)
    }
  }

  Timer {
    id: fileDebounce
    interval: 160
    property string pattern: ""
    property string dir: ""
    property string forQuery: ""
    onTriggered: {
      if (fileProc.running) fileProc.running = false
      fileProc.forQuery = fileDebounce.forQuery
      fileProc.command = [
        "fd", "--hidden", "--follow",
        "--exclude", ".git", "--exclude", "node_modules", "--exclude", ".cache",
        "--max-results", "40",
        "--", fileDebounce.pattern, fileDebounce.dir
      ]
      fileProc.running = true
    }
  }

  Process {
    id: fileProc
    property string forQuery: ""
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.loadFiles(text, fileProc.forQuery)
    }
  }

  Process {
    id: remindersProbe
    command: ["omarchy-reminder", "show", "--json"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.loadReminders(text)
    }
  }

  FileView {
    path: root.home + "/.config/omarchy/spotlight.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.loadSettings(text())
    onFileChanged: reload()
    onLoadFailed: root.loadSettings("{}")
  }

  FileView {
    id: usageFile
    path: root.home + "/.local/state/omarchy/spotlight-usage.json"
    atomicWrites: true
    printErrors: false
    onLoaded: root.loadUsage(text())
    onLoadFailed: root.loadUsage("{}")
  }

  FileView {
    path: root.home + "/.local/state/omarchy/clipboard-history.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.loadClipboard(text())
    onFileChanged: reload()
    onLoadFailed: root.loadClipboard("[]")
  }

  Connections {
    target: root.appLibrary
    function onAppsChanged() { if (root.opened) root.rebuild() }
  }

  ListModel { id: displayModel }

  // A stationary pointer must not own the selection. Without this, opening
  // Spotlight with the cursor anywhere over the list hands the highlight to
  // whatever row happens to land under it, so Enter runs the wrong thing.
  PointerMoveGate {
    id: pointerGate
    referenceItem: pointerFrame
  }

  // ------------------------------------------------------------- surface
  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    // The Hyprland layer rule that frosts this surface matches on this
    // namespace. Renaming it silently turns the glass off.
    WlrLayershell.namespace: "omarchy-spotlight"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle {
      anchors.fill: parent
      color: root.scrim
    }

    // A screen-fixed frame for the pointer gate to measure against. The card
    // is the wrong reference: it animates its height and stays centred, so it
    // slides under a stationary pointer on every rebuild and every row that
    // maps into it reads as deliberate movement.
    Item {
      id: pointerFrame
      anchors.fill: parent
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    Rectangle {
      id: card

      readonly property int listHeight: Math.min(root.maxListHeight, root.contentHeight)
      readonly property bool hasResults: displayModel.count > 0

      width: Math.min(Style.space(750), panel.width - Style.space(48))
      height: root.searchHeight
        + (hasResults ? root.hairline + root.listPadding * 2 + listHeight : 0)
        + root.hairline + root.footerHeight
      // Centred at whatever height it currently is, not just when full. The
      // height Behavior below drives y with it, so the panel grows and
      // shrinks symmetrically about the middle of the screen instead of
      // sitting high whenever a query returns only a few rows.
      anchors.horizontalCenter: parent.horizontalCenter
      anchors.verticalCenter: parent.verticalCenter

      radius: root.cardRadius
      color: root.glassBackground
      border.width: root.hairline
      border.color: root.glassBorder
      antialiasing: true

      Behavior on height {
        NumberAnimation { duration: 110; easing.type: Easing.OutCubic }
      }

      // Swallow clicks so they don't reach the dismiss MouseArea behind.
      MouseArea { anchors.fill: parent; onClicked: {} }

      // The 1px light line along the top edge is what makes a translucent
      // panel read as glass rather than as a flat tint.
      Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        anchors.margins: root.hairline
        height: root.hairline
        color: root.glassSheen
        radius: height
      }

      // ------------------------------------------------------- search row
      Item {
        id: searchRow
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: root.searchHeight

        Text {
          id: searchGlyph
          text: "󰍉"
          textFormat: Text.PlainText
          color: root.foreground
          opacity: 0.5
          font.family: root.fontFamily
          font.pixelSize: root.searchFontSize
          anchors.left: parent.left
          anchors.leftMargin: root.gutter
          anchors.verticalCenter: parent.verticalCenter
        }

        TextInput {
          id: input
          anchors.left: searchGlyph.right
          anchors.leftMargin: Style.space(10)
          anchors.right: parent.right
          anchors.rightMargin: root.gutter
          anchors.verticalCenter: parent.verticalCenter

          color: root.foreground
          selectionColor: Util.alpha(root.accent, 0.35)
          selectedTextColor: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.searchFontSize
          clip: true
          focus: true
          activeFocusOnTab: false
          selectByMouse: true
          inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase

          onTextChanged: root.query = text

          Text {
            anchors.fill: parent
            visible: input.text.length === 0
            text: "Search for apps and commands…"
            textFormat: Text.PlainText
            color: root.foreground
            opacity: 0.38
            font.family: input.font.family
            font.pixelSize: input.font.pixelSize
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
          }

          // BeforeItem so navigation and activation win over text editing;
          // anything not handled here falls through to normal typing, which
          // keeps Ctrl+V, selection and caret movement intact.
          Keys.priority: Keys.BeforeItem
          Keys.onPressed: function(event) {
            typingGuard.restart()
            if (event.key === Qt.Key_Escape) {
              if (input.text.length > 0) input.text = ""
              else root.dismiss()
              event.accepted = true
            } else if (event.key === Qt.Key_Down
                || (event.key === Qt.Key_N && event.modifiers === Qt.ControlModifier)) {
              root.select(1)
              event.accepted = true
            } else if (event.key === Qt.Key_Up
                || (event.key === Qt.Key_P && event.modifiers === Qt.ControlModifier)) {
              root.select(-1)
              event.accepted = true
            } else if (event.key === Qt.Key_PageDown) {
              root.selectPage(1)
              event.accepted = true
            } else if (event.key === Qt.Key_PageUp) {
              root.selectPage(-1)
              event.accepted = true
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
              var secondary = (event.modifiers & Qt.ShiftModifier) || (event.modifiers & Qt.ControlModifier)
              root.activateSelection(secondary ? true : false)
              event.accepted = true
            } else if (event.key === Qt.Key_Tab) {
              // Tab completes the query with the selected row's title, the way
              // a shell completes a path — handy for narrowing an app search.
              var sel = root.selectedRow()
              if (sel && sel.kind === "app") input.text = sel.title
              event.accepted = true
            }
          }
        }
      }

      Rectangle {
        id: searchDivider
        anchors { top: searchRow.bottom; left: parent.left; right: parent.right }
        anchors.leftMargin: root.hairline
        anchors.rightMargin: root.hairline
        height: root.hairline
        color: root.dividerColor
        visible: card.hasResults
      }

      // ------------------------------------------------------- results
      Item {
        anchors {
          top: searchDivider.bottom
          left: parent.left
          right: parent.right
        }
        anchors.topMargin: root.listPadding
        anchors.bottomMargin: root.listPadding
        height: card.listHeight
        visible: card.hasResults

        ListView {
          id: resultList
          anchors.fill: parent
          model: displayModel
          clip: true
          boundsBehavior: Flickable.StopAtBounds
          currentIndex: root.selectedIndex
          highlightMoveDuration: 0

          section.property: "section"
          section.criteria: ViewSection.FullString
          section.delegate: Item {
            required property string section
            width: ListView.view.width
            height: root.sectionHeight

            // Sentence case, not caps: it is what Raycast does, and a
            // tracked-out all-caps label is the tell of a templated UI.
            Text {
              text: parent.section
              textFormat: Text.PlainText
              color: root.foreground
              opacity: 0.45
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              font.weight: Font.Medium
              anchors.left: parent.left
              anchors.leftMargin: root.rowInset + root.listPadding
              anchors.bottom: parent.bottom
              anchors.bottomMargin: Style.space(7)
            }
          }

          // The delegate root spans the full view width and is left where the
          // view puts it: a vertical ListView positions its delegates itself
          // and overwrites any `x` set here, which would push the whole inset
          // to one side. The padding belongs on the surface inside instead.
          delegate: Item {
            id: resultRow
            required property int index
            required property int rowIndex
            required property string rowTitle
            required property string rowSubtitle
            required property string rowAccessory
            required property string rowIcon
            required property string rowImage
            required property bool rowMono
            required property bool selectable

            readonly property bool hasCursor: root.cursorActive && resultRow.index === root.selectedIndex
            readonly property bool armed: root.armedKey.length > 0
              && root.rows[resultRow.rowIndex]
              && root.rows[resultRow.rowIndex].key === root.armedKey

            width: ListView.view.width
            height: root.rowHeight

            Rectangle {
              id: rowSurface
              anchors.fill: parent
              anchors.leftMargin: root.listPadding
              anchors.rightMargin: root.listPadding
              radius: root.rowRadius
              color: resultRow.armed
                ? Util.alpha(Color.urgent, 0.22)
                : (resultRow.hasCursor ? root.selectedBackground : "transparent")
            }

            Image {
              id: rowImageItem
              visible: resultRow.rowImage.length > 0
              source: resultRow.rowImage
              width: Style.space(20)
              height: Style.space(20)
              fillMode: Image.PreserveAspectFit
              sourceSize.width: width * Screen.devicePixelRatio
              sourceSize.height: height * Screen.devicePixelRatio
              asynchronous: true
              anchors.left: rowSurface.left
              anchors.leftMargin: root.rowInset
              anchors.verticalCenter: rowSurface.verticalCenter
            }

            Text {
              id: rowGlyph
              visible: resultRow.rowImage.length === 0
              text: resultRow.rowIcon
              textFormat: Text.PlainText
              color: resultRow.hasCursor ? root.selectedText : root.foreground
              opacity: resultRow.hasCursor ? 1 : 0.75
              font.family: root.fontFamily
              font.pixelSize: Style.font.icon
              width: Style.space(20)
              horizontalAlignment: Text.AlignHCenter
              anchors.left: rowSurface.left
              anchors.leftMargin: root.rowInset
              anchors.verticalCenter: rowSurface.verticalCenter
            }

            Text {
              id: accessoryText
              text: resultRow.armed ? "Press ↵ again to confirm" : resultRow.rowAccessory
              textFormat: Text.PlainText
              color: resultRow.armed ? Color.urgent : root.foreground
              opacity: resultRow.armed ? 1 : 0.38
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              anchors.right: rowSurface.right
              anchors.rightMargin: root.rowInset
              anchors.verticalCenter: rowSurface.verticalCenter
            }

            Row {
              anchors.left: rowGlyph.right
              anchors.leftMargin: Style.space(10)
              anchors.right: accessoryText.left
              anchors.rightMargin: Style.space(14)
              anchors.verticalCenter: rowSurface.verticalCenter
              spacing: Style.space(8)

              Text {
                id: titleText
                text: resultRow.rowTitle
                textFormat: Text.PlainText
                color: resultRow.hasCursor ? root.selectedText : root.foreground
                opacity: resultRow.selectable ? 1 : 0.75
                font.family: resultRow.rowMono ? Style.font.family : root.fontFamily
                font.pixelSize: Style.font.title
                font.weight: resultRow.hasCursor ? Font.Medium : Font.Normal
                elide: Text.ElideRight
                width: Math.min(implicitWidth, parent.width)
                anchors.verticalCenter: parent.verticalCenter
              }

              Text {
                text: resultRow.rowSubtitle
                textFormat: Text.PlainText
                visible: resultRow.rowSubtitle.length > 0 && parent.width - titleText.width > Style.space(60)
                color: root.foreground
                opacity: 0.42
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                elide: Text.ElideRight
                width: Math.max(0, parent.width - titleText.width - Style.space(10))
                anchors.verticalCenter: parent.verticalCenter
              }
            }

            // Fills the visible surface, not the delegate: the click target
            // should be exactly what the highlight shows.
            MouseArea {
              id: rowMouse
              anchors.fill: rowSurface
              hoverEnabled: true
              cursorShape: resultRow.selectable ? Qt.PointingHandCursor : Qt.ArrowCursor
              onEntered: root.selectFromPointer(resultRow.index, resultRow, {
                x: rowMouse.mouseX,
                y: rowMouse.mouseY
              })
              onPositionChanged: function(mouse) {
                root.selectFromPointer(resultRow.index, resultRow, mouse)
              }
              onClicked: function(mouse) {
                if (!resultRow.selectable) return
                root.cursorActive = true
                root.selectedIndex = resultRow.index
                root.activate(resultRow.index, (mouse.modifiers & Qt.ShiftModifier) ? true : false)
              }
            }
          }
        }
      }

      // ------------------------------------------------------- footer
      Rectangle {
        anchors { bottom: footer.top; left: parent.left; right: parent.right }
        anchors.leftMargin: root.hairline
        anchors.rightMargin: root.hairline
        height: root.hairline
        color: root.dividerColor
      }

      Item {
        id: footer
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        anchors.bottomMargin: root.hairline
        height: root.footerHeight

        Text {
          text: "󰣇  Omarchy"
          textFormat: Text.PlainText
          color: root.foreground
          opacity: 0.35
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          anchors.left: parent.left
          anchors.leftMargin: root.gutter
          anchors.verticalCenter: parent.verticalCenter
        }

        Row {
          anchors.right: parent.right
          anchors.rightMargin: root.gutter
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(14)

          Text {
            readonly property var sel: root.selectedRow()
            text: sel && sel.primaryLabel ? "↵  " + sel.primaryLabel : ""
            visible: text.length > 0
            textFormat: Text.PlainText
            color: root.foreground
            opacity: 0.55
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            readonly property var sel: root.selectedRow()
            text: sel && sel.secondaryLabel ? "⇧↵  " + sel.secondaryLabel : ""
            visible: text.length > 0
            textFormat: Text.PlainText
            color: root.foreground
            opacity: 0.4
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }
      }
    }
  }

  // Total height the result list wants, headers included. Driving the card
  // height off this is what gives the panel the Raycast grow/shrink feel.
  readonly property int contentHeight: {
    if (displayModel.count === 0) return 0
    var total = 0
    var lastSection = ""
    for (var i = 0; i < root.rows.length; i++) {
      if (root.rows[i].section !== lastSection) {
        total += root.sectionHeight
        lastSection = root.rows[i].section
      }
      total += root.rowHeight
    }
    return total
  }

  Component.onCompleted: {
    if (root.appLibrary) root.appLibrary.refreshIcons()
  }
}
