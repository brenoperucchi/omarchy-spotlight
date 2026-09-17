const assert = require("node:assert/strict")
const test = require("node:test")
const Chord = require("../lib/Chord.js")

const META = 0x10000000, CTRL = 0x04000000, ALT = 0x08000000, SHIFT = 0x02000000
const KEY_K = 0x4b, KEY_SPACE = 0x20, KEY_F6 = 0x01000035, KEY_ESCAPE = 0x01000000

test("fromEvent spells chords in Hyprland order with one key", () => {
  assert.equal(Chord.fromEvent(KEY_K, SHIFT | META), "SUPER + SHIFT + K")
  assert.equal(Chord.fromEvent(KEY_SPACE, ALT), "ALT + SPACE")
  assert.equal(Chord.fromEvent(KEY_F6, CTRL | ALT), "CTRL + ALT + F6")
  assert.equal(Chord.fromEvent(0x31, META), "SUPER + 1")
})

test("fromEvent refuses bare keys, unknown keys and modifier-only presses", () => {
  assert.equal(Chord.fromEvent(KEY_SPACE, 0), "")
  assert.equal(Chord.fromEvent(KEY_ESCAPE, META), "")
  assert.equal(Chord.fromEvent(0x01000020, META), "")   // Qt.Key_Shift itself
  assert.equal(Chord.fromEvent(0x01000005, META), "")   // keypad Enter
})

test("normalize accepts both spellings and aliases", () => {
  assert.equal(Chord.normalize("SUPER SHIFT CTRL + SPACE"), "SUPER + CTRL + SHIFT + SPACE")
  assert.equal(Chord.normalize("shift+super+k"), "SUPER + SHIFT + K")
  assert.equal(Chord.normalize("Win + Control + Mod1 + F6"), "SUPER + CTRL + ALT + F6")
  assert.equal(Chord.normalize("PRINT"), "PRINT")
  assert.equal(Chord.normalize("SUPER + A + B"), "")
  assert.equal(Chord.normalize("constructor"), "CONSTRUCTOR")
  assert.equal(Chord.normalize(""), "")
})
