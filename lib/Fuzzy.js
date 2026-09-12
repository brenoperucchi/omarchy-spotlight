// Shared text-match tiers. Adjacent tiers are 150 points apart, so the
// bounded 200-point learning bonus may reorder close matches while an exact
// match remains safely ahead of a substantially weaker substring match.

var MATCH_EXACT = 1000
var MATCH_PREFIX = 850
var MATCH_WORD = 700
var MATCH_SUBSTRING = 550
var MATCH_METADATA = 400
var MATCH_RESIDUAL = 250

function normalize(value) {
  return String(value || "").toLowerCase().trim()
}

function acronym(text) {
  var parts = normalize(text).split(/[^a-z0-9]+/)
  var out = ""
  for (var i = 0; i < parts.length; i++) if (parts[i]) out += parts[i].charAt(0)
  return out
}

function atWord(text, query) {
  var from = 0
  while (from < text.length) {
    var index = text.indexOf(query, from)
    if (index < 0) return false
    if (index === 0 || !/[a-z0-9]/.test(text.charAt(index - 1))) return true
    from = index + 1
  }
  return false
}

function termMatches(haystack, titleAcronym, term) {
  return haystack.indexOf(term) >= 0 || titleAcronym.indexOf(term) >= 0
}

// -> { tier, score }, or null when the candidate does not match.
function match(candidate, query) {
  var q = normalize(query)
  if (!q) return { tier: "residual", score: 0 }

  var title = normalize(candidate.title)
  var metadata = normalize([candidate.subtitle, candidate.keywords, candidate.accessory].join(" "))
  var haystack = (title + " " + metadata).trim()
  var ac = acronym(candidate.title)
  var terms = q.split(/\s+/)
  for (var i = 0; i < terms.length; i++) {
    if (!termMatches(haystack, ac, terms[i])) return null
  }

  if (title === q) return { tier: "exact", score: MATCH_EXACT }
  if (title.indexOf(q) === 0) return { tier: "prefix", score: MATCH_PREFIX }
  if (atWord(title, q)) return { tier: "word", score: MATCH_WORD }
  if (title.indexOf(q) >= 0) return { tier: "substring", score: MATCH_SUBSTRING }
  if (metadata.indexOf(q) >= 0 || ac.indexOf(q) >= 0)
    return { tier: "metadata", score: MATCH_METADATA }
  return { tier: "residual", score: MATCH_RESIDUAL }
}

function score(candidate, query) {
  var result = match(candidate, query)
  return result ? result.score : -1
}

function rank(candidates, query, limit) {
  var rows = []
  for (var i = 0; i < candidates.length; i++) {
    var result = match(candidates[i], query)
    if (!result) continue
    rows.push({ row: candidates[i], score: result.score, order: i })
  }
  rows.sort(function(a, b) {
    if (b.score !== a.score) return b.score - a.score
    return a.order - b.order
  })
  var out = []
  var max = limit || rows.length
  for (var j = 0; j < rows.length && out.length < max; j++) out.push(rows[j].row)
  return out
}

if (typeof module !== "undefined") {
  module.exports = {
    match: match, score: score, rank: rank,
    MATCH_EXACT: MATCH_EXACT, MATCH_PREFIX: MATCH_PREFIX, MATCH_WORD: MATCH_WORD,
    MATCH_SUBSTRING: MATCH_SUBSTRING, MATCH_METADATA: MATCH_METADATA,
    MATCH_RESIDUAL: MATCH_RESIDUAL
  }
}
