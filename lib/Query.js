// Parses provider filters without stealing the existing web bangs. In
// particular, `w: firefox` is a window filter while `w firefox` remains a
// Wikipedia search.

var FILTERS = {
  a: "app", app: "app",
  w: "window", window: "window",
  f: "file", file: "file",
  action: "action", cmd: "action",
  cb: "clipboard", clipboard: "clipboard",
  web: "web", search: "web", url: "web",
  calc: "calc",
  unit: "unit", convert: "unit",
  reminder: "reminder",
  calendar: "calendar", event: "calendar"
}

var owned = Object.prototype.hasOwnProperty

function parse(value) {
  var raw = String(value || "").trim()
  var match = raw.match(/^([a-z]+):\s*(.*)$/i)
  if (match) {
    var alias = match[1].toLowerCase()
    if (owned.call(FILTERS, alias)) {
      var filtered = match[2].trim()
      return {
        raw: raw,
        text: filtered,
        filter: FILTERS[alias],
        empty: filtered.length === 0
      }
    }
  }

  // These two space-separated forms predate colon filters and remain
  // exclusive provider choices for compatibility.
  match = raw.match(/^(f|file|files|cb|clip|clipboard)\s+(\S.*)$/i)
  if (match) {
    var legacy = match[1].toLowerCase()
    return {
      raw: raw,
      text: match[2].trim(),
      filter: /^(?:f|file|files)$/.test(legacy) ? "file" : "clipboard",
      empty: false
    }
  }

  return { raw: raw, text: raw, filter: "", empty: false }
}

function contextKeys(query) {
  var text = String(query.text || "").toLowerCase().replace(/\s+/g, " ").trim().slice(0, 200)
  if (text.length < 2) return []
  var namespace = query.filter ? "filter:" + query.filter + ":" : "query:"
  var out = []
  var previous = ""
  for (var i = 2; i <= text.length && out.length < 127; i++) {
    var prefix = text.slice(0, i).trim()
    if (prefix.length >= 2 && prefix !== previous) {
      out.push(namespace + prefix)
      previous = prefix
    }
  }
  var full = namespace + text
  if (out[out.length - 1] !== full) out.push(full)
  return out
}

function contextKey(query) {
  var keys = contextKeys(query)
  return keys.length ? keys[keys.length - 1] : ""
}

if (typeof module !== "undefined") {
  module.exports = { parse: parse, contextKeys: contextKeys, contextKey: contextKey }
}
