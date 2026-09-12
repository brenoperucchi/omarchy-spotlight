var HOUR = 3600000
var DAY = 86400000
var ITEM_KEEP = 400
var FILE_KEEP = 100
var CONTEXT_KEEP = 128
var CONTEXT_HIT_KEEP = 8
var JSON_BUDGET_BYTES = 200000
var owned = Object.prototype.hasOwnProperty

function emptyMap() {
  return Object.create(null)
}

function emptyStore() {
  return { version: 2, items: emptyMap(), contexts: emptyMap() }
}

function decay(ageMs) {
  if (ageMs < HOUR) return 4
  if (ageMs < DAY) return 2
  if (ageMs < 7 * DAY) return 0.5
  if (ageMs < 90 * DAY) return 0.25
  return 0.1
}

function entryRank(entry, now) {
  if (!entry) return 0
  var count = Math.max(0, Number(entry.count) || 0)
  var age = Math.max(0, (Number(now) || Date.now()) - (Number(entry.last) || 0))
  return count * decay(age)
}

function cleanEntry(entry) {
  if (!entry || typeof entry !== "object") return null
  var count = Math.max(0, Number(entry.count) || 0)
  if (!count) return null
  var clean = { count: count, last: Math.max(0, Number(entry.last) || 0) }
  if (entry.meta && typeof entry.meta === "object" && entry.meta.path) {
    clean.meta = {
      path: String(entry.meta.path).slice(0, 1024),
      name: String(entry.meta.name || "").slice(0, 512),
      dir: String(entry.meta.dir || "").slice(0, 1024),
      isDir: entry.meta.isDir === true
    }
  }
  return clean
}

function sortedKeys(map, now) {
  return Object.keys(map || {}).sort(function(a, b) {
    var rankDiff = entryRank(map[b], now) - entryRank(map[a], now)
    if (rankDiff !== 0) return rankDiff
    var lastDiff = (Number(map[b].last) || 0) - (Number(map[a].last) || 0)
    if (lastDiff !== 0) return lastDiff
    return a < b ? -1 : (a > b ? 1 : 0)
  })
}

// QML's JS runtime does not provide TextEncoder, so count the serialized UTF-8
// bytes directly before sending the payload to the helper's byte-capped stdin.
function utf8Bytes(value) {
  var text = String(value || "")
  var bytes = 0
  for (var i = 0; i < text.length; i++) {
    var code = text.charCodeAt(i)
    if (code < 0x80) bytes++
    else if (code < 0x800) bytes += 2
    else if (code >= 0xd800 && code <= 0xdbff
        && i + 1 < text.length && text.charCodeAt(i + 1) >= 0xdc00
        && text.charCodeAt(i + 1) <= 0xdfff) {
      bytes += 4
      i++
    } else bytes += 3
  }
  return bytes
}

function prune(store, now) {
  var next = emptyStore()
  var keys = sortedKeys(store.items, now)
  var files = 0
  var itemCount = 0
  for (var i = 0; i < keys.length && itemCount < ITEM_KEEP; i++) {
    var id = keys[i]
    if (id.indexOf("file:") === 0 && ++files > FILE_KEEP) continue
    next.items[id] = store.items[id]
    itemCount++
  }

  var contexts = []
  var contextKeys = Object.keys(store.contexts || {})
  for (var c = 0; c < contextKeys.length; c++) {
    var source = store.contexts[contextKeys[c]]
    var hits = emptyMap()
    var hitKeys = sortedKeys(source, now)
    var hitCount = 0
    var last = 0
    for (var h = 0; h < hitKeys.length && hitCount < CONTEXT_HIT_KEEP; h++) {
      if (!owned.call(next.items, hitKeys[h])) continue
      hits[hitKeys[h]] = source[hitKeys[h]]
      last = Math.max(last, Number(source[hitKeys[h]].last) || 0)
      hitCount++
    }
    if (!hitCount) continue
    contexts.push({ key: contextKeys[c], hits: hits, last: last })
  }
  contexts.sort(function(a, b) {
    if (b.last !== a.last) return b.last - a.last
    return a.key < b.key ? -1 : (a.key > b.key ? 1 : 0)
  })
  for (var j = 0; j < contexts.length && j < CONTEXT_KEEP; j++)
    next.contexts[contexts[j].key] = contexts[j].hits
  while (utf8Bytes(JSON.stringify(next)) > JSON_BUDGET_BYTES) {
    var contextTail = Object.keys(next.contexts)
    if (contextTail.length) delete next.contexts[contextTail[contextTail.length - 1]]
    else {
      var itemTail = Object.keys(next.items)
      if (!itemTail.length) break
      delete next.items[itemTail[itemTail.length - 1]]
    }
  }
  return next
}

function adopt(parsed, now) {
  var next = emptyStore()
  if (!parsed || typeof parsed !== "object") return next
  var source = parsed.version === 2 && parsed.items ? parsed.items : parsed
  var keys = Object.keys(source || {})
  for (var i = 0; i < keys.length && i < ITEM_KEEP * 4; i++) {
    var id = keys[i]
    if (parsed.version !== 2) {
      if (id.indexOf("cmd:") === 0) id = "action:" + id.slice(4)
      else if (id.indexOf("app:") !== 0) continue
    }
    var entry = cleanEntry(source[keys[i]])
    if (entry) next.items[id] = entry
  }

  if (parsed.version === 2 && parsed.contexts && typeof parsed.contexts === "object") {
    var contextKeys = Object.keys(parsed.contexts)
    for (var c = 0; c < contextKeys.length && c < CONTEXT_KEEP * 4; c++) {
      var hits = emptyMap()
      var rawHits = parsed.contexts[contextKeys[c]]
      var hitKeys = Object.keys(rawHits || {})
      for (var h = 0; h < hitKeys.length && h < CONTEXT_HIT_KEEP * 4; h++) {
        var hit = cleanEntry(rawHits[hitKeys[h]])
        if (hit) hits[hitKeys[h]] = hit
      }
      next.contexts[contextKeys[c]] = hits
    }
  }
  return prune(next, now)
}

function bumpMap(map, id, now, meta) {
  var next = emptyMap()
  var keys = Object.keys(map || {})
  for (var i = 0; i < keys.length; i++) next[keys[i]] = map[keys[i]]
  var previous = owned.call(next, id) ? next[id] : { count: 0 }
  var entry = { count: (Number(previous.count) || 0) + 1, last: now }
  if (meta || previous.meta) entry.meta = meta || previous.meta
  next[id] = entry
  return next
}

function bump(store, id, contextKeys, meta, now) {
  var timestamp = Number(now) || Date.now()
  var next = adopt(store, timestamp)
  next.items = bumpMap(next.items, id, timestamp, meta)
  var keys = contextKeys || []
  for (var i = 0; i < keys.length; i++) {
    var context = String(keys[i] || "")
    if (!context) continue
    next.contexts[context] = bumpMap(next.contexts[context], id, timestamp)
  }
  return prune(next, timestamp)
}

function recencyBonus(entry, now) {
  if (!entry) return 0
  var age = Math.max(0, (Number(now) || Date.now()) - (Number(entry.last) || 0))
  if (age < HOUR) return 40
  if (age < DAY) return 32
  if (age < 7 * DAY) return 20
  if (age < 90 * DAY) return 8
  return 2
}

function frequencyBonus(entry) {
  var count = Math.max(0, Number(entry && entry.count) || 0)
  return count ? 50 * count / (count + 4) : 0
}

function contextBonus(entry, now) {
  var value = entryRank(entry, now)
  return value ? 110 * value / (value + 2) : 0
}

function bonuses(store, id, contextKey, now, enabled) {
  if (!enabled || !id) return { recency: 0, frequency: 0, context: 0 }
  var item = store && store.items && owned.call(store.items, id) ? store.items[id] : null
  var context = store && store.contexts && store.contexts[contextKey]
  var hit = context && owned.call(context, id) ? context[id] : null
  return {
    recency: recencyBonus(item, now),
    frequency: frequencyBonus(item),
    context: contextBonus(hit, now)
  }
}

function hasItem(store, id) {
  return !!(store && store.items && owned.call(store.items, id))
}

if (typeof module !== "undefined") {
  module.exports = {
    emptyStore: emptyStore, adopt: adopt, bump: bump, bonuses: bonuses,
    hasItem: hasItem, utf8Bytes: utf8Bytes
  }
}
