const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const test = require("node:test")
const Commands = require("../lib/Commands.js")
const Fuzzy = require("../lib/Fuzzy.js")

const qml = fs.readFileSync(path.join(__dirname, "..", "Spotlight.qml"), "utf8")

test("the displayed model is one globally ranked, globally capped list", () => {
  assert.match(qml, /next = root\.globallyRank\(next, parsed\.text\)/)
  assert.match(qml, /Util\.clamp\(root\.settings\.maxResults, 8, root\.maxGlobalResults\)/)
  assert.doesNotMatch(qml, /section\.delegate/)
})

test("empty input keeps an application fallback and empty filters show only a hint", () => {
  assert.match(qml, /if \(parsed\.empty\) \{\s*next\.push\(root\.filterHintRow\(parsed\)\)/)
  assert.match(qml, /else if \(!q\) \{\s*push\(root\.idleRows\(\)\)/)
  assert.match(qml, /return root\.appRows\("", false\)/)
  assert.match(qml, /root\.appRows\("", true\)\s*\.concat\(root\.windowRows\("", true\)\)\s*\.concat\(root\.commandRows\("", true, true\)\)\s*\.concat\(root\.learnedFileRows\(\)\)/)
})

test("one character starts only explicitly filtered file and clipboard providers", () => {
  assert.match(qml, /var searchable = parsed\.text\.length >= 2/)
  assert.match(qml, /fileSearchAlways && s\.length >= 2/)
  assert.match(qml, /clipboardSearchAlways && parsed\.text\.length >= 2/)
})

test("spotlight settings finds all four local maintenance actions", () => {
  const rows = Fuzzy.rank(Commands.commands(), "spotlight settings", 20)
    .filter(row => row.key.startsWith("spotlight."))
  assert.deepEqual(rows.map(row => row.title).sort(), [
    "Edit Spotlight Settings",
    "Open Spotlight Data Folder",
    "Open Spotlight Plugin Folder",
    "Reset Spotlight Learning"
  ].sort())
  assert.equal(rows.find(row => row.key === "spotlight.reset").confirm, true)
})

test("every asynchronous query result is rejected after the query changes", () => {
  assert.match(qml, /function loadSuggestions\(raw, forQuery\) \{\s*if \(forQuery !== String\(root\.query/)
  assert.match(qml, /function loadFiles\(raw, forQuery\) \{\s*if \(forQuery !== String\(root\.query/)
  assert.match(qml, /function loadClipboard\(raw, forQuery\) \{\s*if \(forQuery !== String\(root\.query/)
  assert.match(qml, /var restored = root\.pinnedKey \? root\.indexOfKey\(root\.pinnedKey\) : -1/)
  assert.match(qml, /root\.selectedIndex = restored >= 0 \? restored : root\.firstSelectableIndex\(\)/)
})
