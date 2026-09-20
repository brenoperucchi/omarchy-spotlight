const assert = require("node:assert/strict")
const test = require("node:test")
const Query = require("../lib/Query.js")

test("every colon alias selects exactly one provider", () => {
  const aliases = {
    a: "app", app: "app",
    w: "window", window: "window",
    f: "file", file: "file",
    action: "action", cmd: "action",
    cb: "clipboard", clipboard: "clipboard",
    web: "web", search: "web", url: "web",
    calc: "calc",
    unit: "unit", convert: "unit",
    reminder: "reminder",
    calendar: "calendar", event: "calendar",
    man: "tldr", tldr: "tldr"
  }

  for (const [alias, provider] of Object.entries(aliases)) {
    const parsed = Query.parse(`${alias}: needle`)
    assert.equal(parsed.filter, provider, alias)
    assert.equal(parsed.text, "needle", alias)
  }
})

test("empty filters are hints, not unscoped searches", () => {
  for (const alias of ["a", "window", "f", "cmd", "cb", "web", "calc", "unit", "reminder", "event", "man"]) {
    const parsed = Query.parse(`${alias}:`)
    assert.equal(parsed.empty, true, alias)
  }
})

test("space-separated file, clipboard and tldr syntax is exclusive", () => {
  assert.deepEqual(
    { filter: Query.parse("f report").filter, text: Query.parse("f report").text },
    { filter: "file", text: "report" }
  )
  assert.deepEqual(
    { filter: Query.parse("cb ssh").filter, text: Query.parse("cb ssh").text },
    { filter: "clipboard", text: "ssh" }
  )
  assert.deepEqual(
    { filter: Query.parse("man scp").filter, text: Query.parse("man scp").text },
    { filter: "tldr", text: "scp" }
  )
  assert.equal(Query.parse("tldr git commit").text, "git commit")
  assert.equal(Query.parse("tldr: scp").filter, "tldr")
})

test("window colon filter does not steal the Wikipedia bang", () => {
  assert.equal(Query.parse("w: firefox").filter, "window")
  assert.equal(Query.parse("w firefox").filter, "")
  assert.equal(Query.parse("gh quickshell").filter, "")
})

test("query prefixes and colon filters use separate context namespaces", () => {
  assert.deepEqual(Query.contextKeys(Query.parse("Fire")), [
    "query:fi", "query:fir", "query:fire"
  ])
  assert.deepEqual(Query.contextKeys(Query.parse("app: Fire")), [
    "filter:app:fi", "filter:app:fir", "filter:app:fire"
  ])
  assert.equal(Query.contextKey(Query.parse("f report")), "filter:file:report")
  assert.deepEqual(Query.contextKeys(Query.parse("x")), [])
})
