const assert = require("node:assert/strict")
const test = require("node:test")
const FileRank = require("../lib/FileRank.js")

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
