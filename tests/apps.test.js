const assert = require("node:assert/strict")
const test = require("node:test")
const Apps = require("../lib/Apps.js")

test("application fields and result counts are bounded", () => {
  const entries = Array.from({ length: 50 }, (_, i) => ({
    id: `app-${i}`,
    name: "x".repeat(1000) + i,
    keywords: Array(100).fill("keyword")
  }))
  const rows = Apps.sortedEntries(entries, "", null, 7, 12)
  assert.equal(rows.length, 7)
  assert.equal(Apps.entryName(entries[0]).length, 512)
  assert.ok(Apps.entryAcronym(entries[0]).length <= 256)
})

test("hidden ids cannot pollute object prototypes", () => {
  const hidden = Apps.hiddenMap(["__proto__", "constructor"])
  assert.equal(Object.getPrototypeOf(hidden), null)
  assert.equal(hidden.__proto__, true)
  assert.equal(hidden.constructor, true)
  assert.equal({}.polluted, undefined)
})

test("a Chrome web app's generated id does not leak into search text", () => {
  // Real bug: a Chrome PWA's .desktop id is
  // chrome-<32-char extension id>-<profile directory name>, e.g.
  // "chrome-agimnkijcaahngcdmfeangaknmldooml-Default" - every PWA installed
  // under the default Chrome profile was matching the search "default"
  // because entrySearchText() folded that generated id in as if it were a
  // meaningful, human-typed identifier.
  const youtube = { id: "chrome-agimnkijcaahngcdmfeangaknmldooml-Default", name: "YouTube" }
  const text = Apps.entrySearchText(youtube)
  assert.ok(!text.includes("default"), text)
  assert.ok(!text.includes("chrome-"), text)

  // A profile other than "Default" must be excluded the same way - the
  // pattern is the generated id shape, not that one specific string.
  const profile1 = { id: "chrome-agimnkijcaahngcdmfeangaknmldooml-Profile 1", name: "YouTube" }
  assert.ok(!Apps.entrySearchText(profile1).includes("profile"))

  // A normal app's id is still searchable - only the generated PWA shape is
  // excluded, not entry.id in general.
  const firefox = { id: "firefox", name: "Firefox" }
  assert.ok(Apps.entrySearchText(firefox).includes("firefox"))
  const vscode = { id: "code", name: "Visual Studio Code" }
  assert.ok(Apps.entrySearchText(vscode).includes("code"))
})
