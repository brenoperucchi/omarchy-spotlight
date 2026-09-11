// Ranks file/folder results from bin/spotlight-helper's `files` command.
// `fd` has no relevance order of its own - without this, results render in
// whatever order a parallel filesystem walk happened to find them, which is
// not even stable between two runs of the identical query.
//
// This is deliberately a separate scorer from Fuzzy.js, not a second use of
// it: Fuzzy matches a composed haystack (title + subtitle + keywords +
// accessory) and rejects a candidate outright with -1, while a file's match
// has to be judged on the basename alone (the directory is exactly the kind
// of noise that used to let an unrelated deep path outrank the real
// folder) and can never reject - `fd` already decided the candidate
// belongs, this only decides where.

var FILE_TIER_EXACT = 5
var FILE_TIER_PREFIX = 4
var FILE_TIER_WORD = 3
var FILE_TIER_SUBSTRING = 2
var FILE_TIER_RESIDUAL = 1
var FILE_TIER_STEP = 10000

// The search field fires on every keystroke (see fileDebounce in
// Spotlight.qml), so a user spends most of typing with a query that is a
// *prefix* of what they want, not yet equal to it - found in production:
// typing "Downloa" toward "Downloads" ranked the real folder first for four
// keystrokes, then the very next keystroke ("Download", one character
// short of the full name) dropped it to third behind a Go module cache
// that happened to be named exactly "download", then it returned to first
// on the keystroke after that. A full FILE_TIER_STEP gap between EXACT and
// PREFIX means depth/hidden-dotdir penalty (capped well under it, by
// design) can never close that gap, so any shallow cache or build artifact
// whose basename happens to match exactly always wins over a legitimate
// near-complete match, no matter how deep the noise sits or how close the
// real target is to done. This is not specific to plurals: the same
// pattern reproduces for "doc" -> ~/docs, "app" -> ~/Applications, "key"
// -> KeychainHelper.swift, and others - a basename that coincidentally
// equals the query, buried in a cache/toolchain path, beating a shallow
// legitimate target one tier below.
//
// The fix is narrow on purpose: shrink only the EXACT-to-PREFIX gap, not
// the cap itself, so the pathPenalty ceiling and every other tier boundary
// (PREFIX-to-WORD and below) are untouched - a prefix still needs to be
// shallow and un-hidden to have any chance against an exact match, and a
// weak match still cannot climb multiple tiers. 200 leaves roughly 3x
// margin under the shallowest noise measured in production (a 4-level-deep
// cache, 4 * 150 = 600 penalty) without needing to name that cache
// anywhere - depth alone recovers its ranking once this gap stops making
// the comparison moot before penalty is even applied.
var FILE_PREFIX_GAP = 200

function tierBase(tier) {
  if (tier === FILE_TIER_PREFIX) return FILE_TIER_EXACT * FILE_TIER_STEP - FILE_PREFIX_GAP
  return tier * FILE_TIER_STEP
}

// Name-match quality for one term against one basename. A term `fd` only
// admitted through its regex (not a literal hit in the name - a directory
// component, or a multi-term --and match) still gets the lowest tier rather
// than being dropped.
function nameTier(name, term) {
  var n = String(name || "").toLowerCase()
  var t = String(term || "").toLowerCase()
  if (!t) return FILE_TIER_RESIDUAL
  if (n === t) return FILE_TIER_EXACT
  if (n.indexOf(t) === 0) return FILE_TIER_PREFIX
  var idx = n.indexOf(t)
  if (idx < 0) return FILE_TIER_RESIDUAL
  var prev = n.charAt(idx - 1)
  return /[a-z0-9]/i.test(prev) ? FILE_TIER_SUBSTRING : FILE_TIER_WORD
}

// The combined tier is only as good as the term that matches the name
// worst - a term that only matched elsewhere (an --and'd extension inside a
// regex, a directory component) does not get to borrow another term's exact
// hit.
function matchTier(name, terms) {
  var tier = FILE_TIER_EXACT
  for (var i = 0; i < terms.length; i++) {
    tier = Math.min(tier, nameTier(name, terms[i]))
  }
  return tier
}

// Penalty for how far below the searched root a hit sits and whether it
// passes through a dotdir. It is capped below the normal FILE_TIER_STEP, so
// it cannot cross the PREFIX-to-WORD or weaker tier boundaries. The one
// deliberate exception is EXACT-to-PREFIX, whose smaller FILE_PREFIX_GAP
// lets a shallow near-complete target beat a deeply buried exact-name cache
// entry. Computed relative to `searchRoot`, not an absolute segment count,
// so a dotdir the user explicitly navigated into
// (`~/.config/retroarch/...`) is not penalized for being hidden or deep -
// only what lies below the root they chose is.
function pathPenalty(dir, name, searchRoot) {
  // Not `root`: this file has no .pragma library, so it runs in the
  // importing QML document's scope, where `root` is Spotlight.qml's own
  // Item id. Shadowing it here is harmless today (nothing below reads
  // `root.anything`) but is exactly the kind of name a future edit reaches
  // for by habit and gets silently the wrong one.
  var base = String(searchRoot || "").replace(/\/+$/, "")
  var d = String(dir || "")
  var rel = d.indexOf(base) === 0 ? d.slice(base.length) : d
  var segments = rel.split("/").filter(function(s) { return s.length > 0 })
  var hiddenAncestor = segments.some(function(s) { return s.charAt(0) === "." })
  var hiddenName = String(name || "").charAt(0) === "."
  var penalty = segments.length * 150 + (hiddenAncestor ? 1500 : 0) + (hiddenName ? 500 : 0)
  return Math.min(penalty, FILE_TIER_STEP - 1)
}

// Ranks `list` (helper file/dir rows: {path, name, dir, isDir}), best first.
// Deterministic on ties: normalized path, then the original path, never the
// arrival order `fd`'s walk produced. `maxTerms`, if given, should match the
// helper's own term cap for callers that split a query into multiple --and
// patterns - a query with more terms than the helper actually used to
// filter must not be scored on terms `fd` never saw, or every candidate
// collapses to the same residual tier and the name-match signal disappears
// entirely. Omit it where the helper does not cap terms.
function rank(list, pattern, searchRoot, maxTerms) {
  var terms = String(pattern || "").split(/\s+/).filter(function(s) { return s.length > 0 })
  if (maxTerms > 0) terms = terms.slice(0, maxTerms)
  var browsing = terms.length === 0 || (terms.length === 1 && terms[0] === ".")
  var scored = list.map(function(f) {
    var tier = browsing ? FILE_TIER_EXACT : matchTier(f.name, terms)
    var penalty = pathPenalty(f.dir, f.name, searchRoot)
    return { f: f, score: tierBase(tier) - penalty }
  })
  scored.sort(function(a, b) {
    if (b.score !== a.score) return b.score - a.score
    var an = (a.f.path || "").toLowerCase()
    var bn = (b.f.path || "").toLowerCase()
    if (an !== bn) return an < bn ? -1 : 1
    var ao = a.f.path || ""
    var bo = b.f.path || ""
    if (ao < bo) return -1
    if (ao > bo) return 1
    return 0
  })
  return scored.map(function(s) { return s.f })
}

if (typeof module !== "undefined") {
  module.exports = {
    nameTier: nameTier,
    matchTier: matchTier,
    pathPenalty: pathPenalty,
    rank: rank,
    FILE_TIER_EXACT: FILE_TIER_EXACT,
    FILE_TIER_PREFIX: FILE_TIER_PREFIX,
    FILE_TIER_WORD: FILE_TIER_WORD,
    FILE_TIER_SUBSTRING: FILE_TIER_SUBSTRING,
    FILE_TIER_RESIDUAL: FILE_TIER_RESIDUAL,
    FILE_TIER_STEP: FILE_TIER_STEP,
    FILE_PREFIX_GAP: FILE_PREFIX_GAP
  }
}
