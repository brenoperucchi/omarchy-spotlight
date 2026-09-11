const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const test = require("node:test")
const FileRank = require("../lib/FileRank.js")

const ROOT = path.join(__dirname, "..")

function file(path, isDir) {
  var slash = path.lastIndexOf("/")
  return {
    path: path,
    name: slash >= 0 ? path.slice(slash + 1) : path,
    dir: slash > 0 ? path.slice(0, slash) : "/",
    isDir: isDir === true
  }
}

test("the real folder outranks noise buried in dotdirs, deterministically", () => {
  const list = [
    file("/home/x/.claude/downloads", true),
    file("/home/x/.grok/downloads", true),
    file("/home/x/.config/retroarch/downloads", true),
    file("/home/x/Downloads", true)
  ]
  const ranked = FileRank.rank(list, "Downloads", "/home/x", 8)
  assert.equal(ranked[0].path, "/home/x/Downloads")
  // Repeated runs over the same input must agree - this is what fixes a
  // launcher result flip-flopping between keystrokes.
  const again = FileRank.rank(list.slice().reverse(), "Downloads", "/home/x", 8)
  assert.deepEqual(ranked.map(f => f.path), again.map(f => f.path))
})

test("match tier is judged on the basename, never the directory", () => {
  // A deep, unrelated snapshot path containing the query term in `dir`
  // must not outrank a shallow exact name match.
  const list = [
    file("/home/x/.claude/projects/-home-x-Downloads-Contratos-Thera", true),
    file("/home/x/Downloads", true)
  ]
  const ranked = FileRank.rank(list, "Downloads", "/home/x", 8)
  assert.equal(ranked[0].path, "/home/x/Downloads")
})

test("path depth and hidden segments are a bounded penalty, never a tier crossing", () => {
  // An exact match buried arbitrarily deep in hidden directories must still
  // never lose to a merely-substring match near the root - the penalty is
  // capped under one tier step.
  const deepExact = file("/home/x/.a/.b/.c/.d/.e/.f/.g/.h/.i/.j/downloads", true)
  const shallowSubstring = file("/home/x/my-downloads-archive", true)
  const ranked = FileRank.rank([shallowSubstring, deepExact], "downloads", "/home/x", 8)
  assert.equal(ranked[0].path, deepExact.path)
})

test("depth/hidden penalty is relative to the searched root, not absolute", () => {
  // A dotdir the user explicitly navigated into is not penalized for being
  // hidden - only what lies below the root they searched is.
  const p = FileRank.pathPenalty("/home/x/.config/retroarch", "downloads", "/home/x/.config/retroarch")
  assert.equal(p, 0)
})

test("multi-term: the combined tier is the weakest matching term", () => {
  const list = [
    file("/home/x/docs/PMJ Analise Investimentos.xlsx"),
    file("/home/x/docs/PMJ Notas.txt")
  ]
  const ranked = FileRank.rank(list, "PMJ XLS", "/home/x", 8)
  assert.equal(ranked[0].path, list[0].path)
})

test("terms beyond maxTerms are not scored - matches the helper's own cutoff", () => {
  const list = [file("/home/x/Downloads")]
  const manyTerms = "Downloads " + Array(10).fill("zzz").join(" ")
  // Without the cap, term #9+ (never seen by the helper) would drag this
  // candidate to the residual tier even though the name is an exact match.
  const ranked = FileRank.rank(list, manyTerms, "/home/x", 1)
  assert.equal(FileRank.matchTier(list[0].name, ["downloads"]), FileRank.FILE_TIER_EXACT)
  assert.equal(ranked[0].path, list[0].path)
})

test("a term fd admitted only via regex still ranks, never dropped", () => {
  const list = [file("/home/x/report.xlsx"), file("/home/x/notes.txt")]
  const ranked = FileRank.rank(list, "\\.xlsx$", "/home/x", 8)
  assert.equal(ranked.length, 2)
})

test("browsing (path-typed, pattern '.') still applies the path penalty", () => {
  // Regression: browsing must skip the *tier* (there is no term to match)
  // but not the *penalty* - depth/hidden still has to separate a shallow
  // top-level entry from something buried in a subdirectory.
  const list = [
    file("/home/x/Devs/omarchy-spotlight/deep/nested/thing.txt"),
    file("/home/x/Devs/top-level-project", true)
  ]
  const ranked = FileRank.rank(list, ".", "/home/x/Devs", 8)
  assert.equal(ranked[0].path, "/home/x/Devs/top-level-project")
})

test("ties are broken by path, never by fd's arrival order", () => {
  const a = file("/home/x/Downloads")
  const b = file("/home/x/downloads")
  const forward = FileRank.rank([a, b], "downloads", "/home/x", 8)
  const reversed = FileRank.rank([b, a], "downloads", "/home/x", 8)
  assert.deepEqual(forward.map(f => f.path), reversed.map(f => f.path))
})

test("a shallow near-complete prefix outranks an exact match buried in cache/toolchain noise", () => {
  // Reproduces the production case: typing "Download" toward "Downloads"
  // used to drop the real folder to third behind a Go module cache
  // directory that happened to be named exactly "download", four levels
  // below $HOME (4 * 150 = 600 penalty) - a full FILE_TIER_STEP gap between
  // EXACT and PREFIX meant no depth penalty could ever close it.
  const target = file("/home/x/Downloads", true)
  const cache = file("/home/x/go/pkg/mod/cache/download", true)
  const ranked = FileRank.rank([cache, target], "Download", "/home/x", 8)
  assert.equal(ranked[0].path, target.path)
})

test("the prefix gap is narrow: a merely-deep exact match still beats a shallow prefix", () => {
  // The fix narrows one specific boundary, it does not flatten tiers in
  // general - an exact match only one level deep (150 penalty, comfortably
  // more than FILE_PREFIX_GAP=200 away from mattering here) still loses to
  // nothing: it should still outrank a same-depth prefix match.
  const exactOneLevelDeep = file("/home/x/sub/download", true)
  const prefixShallow = file("/home/x/downloads", true)
  const ranked = FileRank.rank([prefixShallow, exactOneLevelDeep], "download", "/home/x", 8)
  assert.equal(ranked[0].path, exactOneLevelDeep.path)
})

test("an exact match noise directory only two levels deep already loses to a shallow prefix", () => {
  // Sanity check on the calibration: FILE_PREFIX_GAP (200) is well under
  // two levels of depth penalty (2 * 150 = 300), so even fairly shallow
  // noise no longer wins once it stops being exactly at the search root.
  const noiseTwoLevelsDeep = file("/home/x/a/b/download", true)
  const target = file("/home/x/Downloads", true)
  const ranked = FileRank.rank([noiseTwoLevelsDeep, target], "Download", "/home/x", 8)
  assert.equal(ranked[0].path, target.path)
})

test("the prefix gap does not distort ordering between two same-tier candidates", () => {
  // FILE_PREFIX_GAP is a constant offset applied identically to every
  // PREFIX-tier candidate, so two candidates that are both merely prefixes
  // (a one-letter query never produces an EXACT match against a longer
  // real name) still rank purely by depth/hidden penalty and the path
  // tiebreak, exactly as before the gap was introduced - a naive
  // alternative that priced the "leftover" characters of a match was found
  // to regress exactly this case (a short query re-sorting by name length
  // instead of depth).
  const shallow = file("/home/x/docs", true)
  const deeper = file("/home/x/sub/downloads", true)
  const ranked = FileRank.rank([deeper, shallow], "D", "/home/x", 8)
  assert.equal(ranked[0].path, shallow.path)
})

test("the production call site passes fileMaxTerms, matching the helper's own cutoff", () => {
  // Flagged in maintainer review on the PR: main's multi-term change AND-filters bin/spotlight-
  // helper's `fd` call on the first FILES_MAX_TERMS (8) terms, but this
  // branch's production loadFiles() call to FileRank.rank() had no
  // corresponding argument at all - an omitted maxTerms silently degrades
  // to rank()'s no-cap default rather than failing loudly, so nothing here
  // short of reading the actual call site (the unit tests above only
  // exercise the scorer API, never this file) would have caught it. This
  // is a text check, not a QML runtime one - there is no QML test harness
  // in this repo - but it pins both the constant and the call shape so a
  // stale comment or a dropped argument fails a test instead of shipping.
  const qml = fs.readFileSync(path.join(ROOT, "Spotlight.qml"), "utf8")
  const helper = fs.readFileSync(path.join(ROOT, "bin", "spotlight-helper"), "utf8")

  const qmlMatch = qml.match(/readonly property int fileMaxTerms:\s*(\d+)/)
  assert.ok(qmlMatch, "Spotlight.qml must declare a fileMaxTerms property")

  const helperMatch = helper.match(/^FILES_MAX_TERMS = (\d+)/m)
  assert.ok(helperMatch, "bin/spotlight-helper must declare FILES_MAX_TERMS")

  assert.equal(
    qmlMatch[1],
    helperMatch[1],
    "Spotlight.qml's fileMaxTerms must match the helper's FILES_MAX_TERMS"
  )
  assert.match(
    qml,
    /FileRank\.rank\(candidates, target\.pattern, target\.dir, root\.fileMaxTerms\)/,
    "the production loadFiles() call must pass root.fileMaxTerms to FileRank.rank()"
  )
})
