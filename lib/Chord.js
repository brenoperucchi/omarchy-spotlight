// Keyboard chords spelled the way Hyprland's Lua bindings spell them:
// "SUPER + SHIFT + K". Numeric Qt constants so `node --test` needs no Qt.

var MODS = [
  [0x10000000, "SUPER"],   // Qt.MetaModifier
  [0x04000000, "CTRL"],    // Qt.ControlModifier
  [0x08000000, "ALT"],     // Qt.AltModifier
  [0x02000000, "SHIFT"]    // Qt.ShiftModifier
]

var KEYS = {
  0x20: "SPACE",           // Qt.Key_Space
  0x01000001: "TAB",       // Qt.Key_Tab
  0x01000002: "TAB",       // Qt.Key_Backtab: Shift+Tab arrives as this
  0x01000003: "BACKSPACE",
  0x01000004: "RETURN",    // Qt.Key_Enter (keypad) stays unmapped: Hyprland calls it KP_Enter
  0x01000007: "DELETE",
  0x01000009: "PRINT",
  0x01000012: "LEFT",
  0x01000013: "UP",
  0x01000014: "RIGHT",
  0x01000015: "DOWN"
}

var owned = Object.prototype.hasOwnProperty

function keyName(key) {
  if (owned.call(KEYS, key)) return KEYS[key]
  if ((key >= 0x41 && key <= 0x5a) || (key >= 0x30 && key <= 0x39)) return String.fromCharCode(key)
  if (key >= 0x01000030 && key <= 0x0100003b) return "F" + (key - 0x01000030 + 1)   // Qt.Key_F1..F12
  return ""
}

// Key event -> canonical chord, or "" when the key is unknown or no
// modifier is held (a bare key is never a launcher shortcut).
function fromEvent(key, modifiers) {
  var name = keyName(key)
  if (name === "") return ""
  var parts = []
  for (var i = 0; i < MODS.length; i++)
    if (modifiers & MODS[i][0]) parts.push(MODS[i][1])
  if (parts.length === 0) return ""
  parts.push(name)
  return parts.join(" + ")
}

var ALIASES = { WIN: "SUPER", LOGO: "SUPER", MOD4: "SUPER", CONTROL: "CTRL", MOD1: "ALT" }
var ORDER = ["SUPER", "CTRL", "ALT", "SHIFT"]

// Both spellings in the wild -> canonical: `omarchy-menu-keybindings --print`
// writes "SUPER SHIFT CTRL + SPACE", bindings.lua writes "SUPER + SHIFT + K".
// Does not validate the key; "" when there is not exactly one.
function normalize(text) {
  var tokens = String(text || "").toUpperCase().split(/[\s+]+/).filter(Boolean)
  var mods = [], keys = []
  for (var i = 0; i < tokens.length; i++) {
    var t = owned.call(ALIASES, tokens[i]) ? ALIASES[tokens[i]] : tokens[i]
    if (ORDER.indexOf(t) >= 0) { if (mods.indexOf(t) < 0) mods.push(t) }
    else keys.push(t)
  }
  if (keys.length !== 1) return ""
  var out = ORDER.filter(function(m) { return mods.indexOf(m) >= 0 })
  out.push(keys[0])
  return out.join(" + ")
}

if (typeof module !== "undefined") {
  module.exports = { fromEvent: fromEvent, normalize: normalize }
}
