const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const test = require("node:test")
const Commands = require("../lib/Commands.js")

const helper = fs.readFileSync(path.join(__dirname, "..", "bin", "spotlight-helper"), "utf8")
const entries = Commands.commands().concat(Commands.quicklinks())

test("a catalogue key names exactly one entry", () => {
  const seen = new Set()
  for (const c of entries) {
    assert.equal(typeof c.key, "string")
    assert.ok(c.key.length > 0)
    assert.ok(!seen.has(c.key), "duplicate key " + c.key)
    seen.add(c.key)
  }
})

test("every shell entry carries a runnable argv vector", () => {
  for (const c of entries.filter(e => e.kind === "shell")) {
    const pair = Array.isArray(c.argvOn) && Array.isArray(c.argvOff)
    assert.ok(Array.isArray(c.argv) || pair, c.key + " has neither argv nor an argvOn/argvOff pair")
    for (const argv of [c.argv, c.argvOn, c.argvOff].filter(Array.isArray)) {
      assert.ok(argv.length > 0, c.key + " has an empty argv")
      for (const token of argv) assert.equal(typeof token, "string")
    }
  }
})

test("every state id is one the helper knows how to probe", () => {
  const stateful = entries.filter(c => c.state)
  assert.ok(stateful.length > 0)
  for (const c of stateful) {
    assert.equal(c.kind, "shell", c.key + " is not a shell entry")
    assert.match(helper, new RegExp('"' + c.state + '":'), "helper cannot probe " + c.state)
  }
})

test("a toggle without a toggle verb declares both directions", () => {
  // argvOn on its own would leave the row able to turn the setting on and
  // never off, which is worse than the plain action row it replaced.
  for (const c of entries) {
    assert.equal(Array.isArray(c.argvOn), Array.isArray(c.argvOff), c.key + " declares only one direction")
    if (Array.isArray(c.argvOn)) assert.ok(c.state, c.key + " has directions but no state to read")
  }
})

test("argvId collapses the menu spelling of a command onto the catalogue one", () => {
  assert.equal(Commands.argvId(["omarchy", "toggle", "nightlight"]), "omarchy-toggle-nightlight")
  assert.equal(Commands.argvId(["omarchy-toggle-nightlight"]), "omarchy-toggle-nightlight")
  assert.equal(Commands.argvId(["omarchy-audio-output-volume", "mute-toggle"]),
    Commands.argvId(["omarchy", "audio", "output", "volume", "mute-toggle"]))
  assert.equal(Commands.argvId(null), "")
  assert.equal(Commands.argvId([]), "")
})
