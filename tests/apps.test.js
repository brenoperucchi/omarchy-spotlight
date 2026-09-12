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

test("a browser-installed web app's generated id does not leak into search text or acronym", () => {
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
  // entryAcronym folded the id in too ("ytcad" instead of "yt") - same fix.
  assert.equal(Apps.entryAcronym(youtube), "yt")

  // A profile other than "Default" must be excluded the same way - the
  // pattern is the generated id shape, not that one specific string.
  const profile1 = { id: "chrome-agimnkijcaahngcdmfeangaknmldooml-Profile 1", name: "YouTube" }
  assert.ok(!Apps.entrySearchText(profile1).includes("profile"))

  // omarchy-launch-webapp installs the same id shape for other Chromium-
  // based browsers - the invariant is the 32-letter extension id, not the
  // "chrome-" prefix.
  const brave = { id: "brave-agimnkijcaahngcdmfeangaknmldooml-Default", name: "YouTube" }
  assert.ok(!Apps.entrySearchText(brave).includes("default"))

  // A normal app's id is still searchable - only the generated webapp shape
  // is excluded, not entry.id in general.
  const firefox = { id: "firefox", name: "Firefox" }
  assert.ok(Apps.entrySearchText(firefox).includes("firefox"))
  const vscode = { id: "code", name: "Visual Studio Code" }
  assert.ok(Apps.entrySearchText(vscode).includes("code"))
})

test("a generated web app id does not win a match through score() either", () => {
  // Found by review: the first fix only closed entrySearchText() - termMatches()
  // and score() read entry.id raw, independent of entrySearchText(), so the
  // PWA still matched "default" with a high score even after that fix.
  const youtube = { id: "chrome-agimnkijcaahngcdmfeangaknmldooml-Default", name: "YouTube" }
  assert.equal(Apps.score(youtube, "default"), -1)
  // A real, human id is still a legitimate match.
  assert.ok(Apps.score({ id: "firefox", name: "Firefox" }, "firefox") > 0)
})

test("isHidden accepts a callback, not just a map, for the AppLibrary path", () => {
  // Spotlight passes root.appLibrary.isHiddenEntry directly when the shell's
  // AppLibrary is available (it combines two hiding sources Spotlight has
  // no other way to read) - sortedEntries() must honour that callback the
  // same way it honours a plain id->true map.
  const entries = [{ id: "hidden-app", name: "Hidden" }, { id: "shown-app", name: "Shown" }]
  const callback = (entry) => entry.id === "hidden-app"
  const rows = Apps.sortedEntries(entries, "", callback, 10, 10)
  assert.deepEqual(rows.map(r => r.entry.id), ["shown-app"])
})
