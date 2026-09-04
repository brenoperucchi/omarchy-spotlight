// The system / Omarchy command catalogue. Every entry is data: the QML side
// dispatches on `kind` and never evaluates a string from here as QML.
//
//   kind "shell"  -> run through a login shell (needed for the omarchy PATH)
//   kind "summon" -> hand off to another shell plugin over IPC
//   kind "url"    -> open in the default browser

function commands() {
  return [
    // ---------------------------------------------------------- capture
    { key: "cap.region",  title: "Screenshot Region",        subtitle: "Select an area",              icon: "󰩭", kind: "shell", cmd: "omarchy capture screenshot region",     keywords: "screenshot screen capture snip grab area" },
    { key: "cap.window",  title: "Screenshot Window",        subtitle: "Pick a window",               icon: "󰹑", kind: "shell", cmd: "omarchy capture screenshot windows",    keywords: "screenshot window capture" },
    { key: "cap.full",    title: "Screenshot Full Screen",   subtitle: "Whole display",               icon: "󰹑", kind: "shell", cmd: "omarchy capture screenshot fullscreen", keywords: "screenshot fullscreen display capture" },
    { key: "cap.text",    title: "Capture Text (OCR)",       subtitle: "Read text off the screen",    icon: "󰚞", kind: "shell", cmd: "omarchy capture text",                  keywords: "ocr text extract copy read" },
    { key: "cap.qr",      title: "Scan QR Code",             subtitle: "Decode from a region",        icon: "󰐲", kind: "shell", cmd: "omarchy capture qr",                    keywords: "qr code scan decode barcode" },
    { key: "cap.rec",     title: "Start Screen Recording",   subtitle: "Record a region",             icon: "󰑊", kind: "shell", cmd: "omarchy capture screenrecording",       keywords: "record recording video screencast" },
    { key: "cap.recfull", title: "Record Full Screen",       subtitle: "Record the whole display",    icon: "󰑊", kind: "shell", cmd: "omarchy capture screenrecording --fullscreen", keywords: "record recording video fullscreen" },
    { key: "cap.recstop", title: "Stop Screen Recording",    subtitle: "End the active recording",    icon: "󰙦", kind: "shell", cmd: "omarchy capture screenrecording --stop-recording", keywords: "stop record recording end" },

    // ---------------------------------------------------------- appearance
    { key: "theme.pick",  title: "Change Theme",             subtitle: "Open the theme switcher",     icon: "󰸌", kind: "shell", cmd: "omarchy theme switcher",       keywords: "theme colors colours appearance style dark light" },
    { key: "theme.bg",    title: "Change Background",        subtitle: "Open the wallpaper picker",   icon: "󰸉", kind: "shell", cmd: "omarchy theme bg-switcher",    keywords: "wallpaper background image desktop" },
    { key: "theme.bgnext",title: "Next Background",          subtitle: "Cycle the wallpaper",         icon: "󰵦", kind: "shell", cmd: "omarchy theme bg next",        keywords: "wallpaper background next cycle" },
    { key: "theme.font",  title: "Change Font",              subtitle: "Pick the system monospace",   icon: "󰛖", kind: "shell", cmd: "omarchy menu font",            keywords: "font typeface monospace typography" },
    { key: "night",       title: "Toggle Night Light",       subtitle: "Warm the screen",             icon: "󰖔", kind: "shell", cmd: "omarchy toggle nightlight",    keywords: "nightlight blue light warm temperature gamma" },
    { key: "bar.toggle",  title: "Toggle Status Bar",        subtitle: "Show or hide the bar",        icon: "󱂪", kind: "shell", cmd: "omarchy toggle bar",           keywords: "bar status hide show topbar" },

    // ---------------------------------------------------------- shell surfaces
    { key: "sum.emoji",   title: "Emoji Picker",             subtitle: "Search and insert emoji",     icon: "󰞅", kind: "summon", id: "omarchy.emojis",    keywords: "emoji emoticon smiley symbol insert" },
    { key: "sum.clip",    title: "Clipboard History",        subtitle: "Browse and paste history",    icon: "󰅌", kind: "summon", id: "omarchy.clipboard", keywords: "clipboard history paste copy" },
    { key: "sum.remind",  title: "Set a Reminder…",          subtitle: "Open the reminder picker",    icon: "󰢌", kind: "summon", id: "omarchy.reminders", keywords: "reminder timer alarm notify remind" },
    { key: "sum.menu",    title: "Omarchy Menu",             subtitle: "The full command menu",       icon: "󰣇", kind: "summon", id: "omarchy.menu",      keywords: "omarchy menu root commands" },
    { key: "keys",        title: "Keybindings",              subtitle: "Search Hyprland keybindings", icon: "󰌌", kind: "shell", cmd: "omarchy menu keybindings", keywords: "keybinding shortcut keys hotkey hyprland" },

    // ---------------------------------------------------------- windows / layout
    { key: "win.gaps",    title: "Toggle Window Gaps",       subtitle: "Zero gaps or default",        icon: "󰆾", kind: "shell", cmd: "omarchy hyprland window gaps toggle",            keywords: "gaps spacing window layout" },
    { key: "win.trans",   title: "Toggle Window Transparency", subtitle: "For the focused window",    icon: "󰆧", kind: "shell", cmd: "omarchy hyprland window transparency toggle",    keywords: "transparency opacity window focused" },
    { key: "win.layout",  title: "Toggle Workspace Layout",  subtitle: "Dwindle or scrolling",        icon: "󰕰", kind: "shell", cmd: "omarchy hyprland workspace layout toggle",       keywords: "layout dwindle scrolling tiling workspace" },
    { key: "win.tfs",     title: "Toggle Tiled Fullscreen",  subtitle: "For the focused window",      icon: "󰊓", kind: "shell", cmd: "omarchy hyprland window tiled fullscreen toggle", keywords: "fullscreen tiled maximize window" },

    // ---------------------------------------------------------- devices
    { key: "dev.touchpad",title: "Toggle Touchpad",          subtitle: "Enable or disable",           icon: "󰟸", kind: "shell", cmd: "omarchy toggle touchpad",   keywords: "touchpad trackpad input disable" },
    { key: "dev.dnd",     title: "Toggle Do Not Disturb",    subtitle: "Silence notifications",       icon: "󰂛", kind: "shell", cmd: "omarchy toggle notification silencing", keywords: "notification silence dnd disturb mute quiet" },
    { key: "dev.idle",    title: "Toggle Stay Awake",        subtitle: "Inhibit idle and lock",       icon: "󰅶", kind: "shell", cmd: "omarchy toggle idle",       keywords: "idle awake caffeine sleep inhibit lock" },
    { key: "dev.bt",      title: "Toggle Bluetooth",         subtitle: "Radio on or off",             icon: "󰂯", kind: "shell", cmd: "omarchy bluetooth power toggle", keywords: "bluetooth radio wireless pair" },

    // ---------------------------------------------------------- apps and places
    { key: "run.files",   title: "Files",                    subtitle: "Open the file manager",       icon: "󰉋", kind: "shell", cmd: "omarchy launch nautilus",   keywords: "files nautilus explorer folder browse" },
    { key: "run.term",    title: "Terminal",                 subtitle: "Open a terminal",             icon: "󰆍", kind: "shell", cmd: "omarchy launch terminal",   keywords: "terminal shell console alacritty" },
    { key: "run.editor",  title: "Editor",                   subtitle: "Open the default editor",     icon: "󰅩", kind: "shell", cmd: "omarchy launch editor",     keywords: "editor code nvim vim ide" },
    { key: "run.about",   title: "About This System",        subtitle: "fastfetch system info",       icon: "󰋼", kind: "shell", cmd: "omarchy launch about",      keywords: "about system info fastfetch specs version" },
    { key: "run.saver",   title: "Screensaver",              subtitle: "Start it now",                icon: "󰹑", kind: "shell", cmd: "omarchy launch screensaver",keywords: "screensaver saver idle animation" },

    // ---------------------------------------------------------- maintenance
    { key: "sys.update",  title: "Update Omarchy & Packages",subtitle: "Full system update",          icon: "󰚰", kind: "shell", cmd: "omarchy launch tui omarchy-update", keywords: "update upgrade packages pacman system" },
    { key: "sys.shellres",title: "Restart Omarchy Shell",    subtitle: "Bar, notifications, panels",  icon: "󰜉", kind: "shell", cmd: "omarchy restart shell",     keywords: "restart shell bar quickshell reload" },
    { key: "sys.hypr",    title: "Reload Hyprland Config",   subtitle: "Re-read the Lua config",      icon: "󰑓", kind: "shell", cmd: "hyprctl reload",            keywords: "reload hyprland config compositor" },

    // ---------------------------------------------------------- session
    { key: "ses.lock",    title: "Lock Screen",              subtitle: "Lock and blank the display",  icon: "󰌾", kind: "shell", cmd: "omarchy system lock",       keywords: "lock screen session secure away" },
    { key: "ses.suspend", title: "Suspend",                  subtitle: "Sleep the machine",           icon: "󰤄", kind: "shell", cmd: "systemctl suspend",         keywords: "suspend sleep standby s3" },
    { key: "ses.logout",  title: "Log Out",                  subtitle: "End the session",             icon: "󰗽", kind: "shell", cmd: "omarchy system logout",     keywords: "logout log out sign out exit session", confirm: true },
    { key: "ses.reboot",  title: "Restart",                  subtitle: "Reboot the machine",          icon: "󰜉", kind: "shell", cmd: "omarchy system reboot",     keywords: "reboot restart", confirm: true },
    { key: "ses.off",     title: "Shut Down",                subtitle: "Power off",                   icon: "󰐥", kind: "shell", cmd: "omarchy system shutdown",   keywords: "shutdown power off halt", confirm: true }
  ]
}

// Named destinations, the Raycast "Quicklinks" idea in miniature.
function quicklinks() {
  return [
    { key: "ql.manual",  title: "Omarchy Manual",  subtitle: "manuals.omamix.org", icon: "󰣇", kind: "url", url: "https://manuals.omamix.org/2/the-omarchy-manual", keywords: "omarchy manual docs help handbook" },
    { key: "ql.hypr",    title: "Hyprland Wiki",   subtitle: "wiki.hypr.land",     icon: "󰖟", kind: "url", url: "https://wiki.hypr.land/",                        keywords: "hyprland wiki docs config" },
    { key: "ql.archwiki",title: "Arch Wiki",       subtitle: "wiki.archlinux.org", icon: "󰣇", kind: "url", url: "https://wiki.archlinux.org/",                    keywords: "arch wiki linux docs" },
    { key: "ql.github",  title: "GitHub",          subtitle: "github.com",         icon: "󰊤", kind: "url", url: "https://github.com/",                            keywords: "github git repos code" },
    { key: "ql.mail",    title: "Gmail",           subtitle: "mail.google.com",    icon: "󰊫", kind: "url", url: "https://mail.google.com/",                       keywords: "mail email gmail inbox" },
    { key: "ql.cal",     title: "Google Calendar", subtitle: "calendar.google.com",icon: "󰸗", kind: "url", url: "https://calendar.google.com/",                   keywords: "calendar google events schedule agenda" }
  ]
}
