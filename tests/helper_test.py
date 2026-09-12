import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "bin" / "spotlight-helper"
SPEC = importlib.util.spec_from_file_location("spotlight_helper", HELPER_PATH)
if SPEC is None:
    from importlib.machinery import SourceFileLoader

    SPEC = importlib.util.spec_from_loader(
        "spotlight_helper", SourceFileLoader("spotlight_helper", str(HELPER_PATH))
    )
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class HelperTests(unittest.TestCase):
    def test_settings_are_private_by_default_and_bounded(self):
        defaults = HELPER.normalize_settings({})
        self.assertFalse(defaults["webSuggestions"])
        self.assertTrue(defaults["fileSearchAlways"])
        self.assertTrue(defaults["clipboardSearch"])
        self.assertTrue(defaults["clipboardSearchAlways"])
        self.assertTrue(defaults["learningEnabled"])
        self.assertEqual(defaults["maxResults"], 20)

        settings = HELPER.normalize_settings({
            "webSuggestions": "yes",
            "maxApps": 999,
            "maxSuggestions": -5,
            "maxResults": 999,
            "learningEnabled": False,
            "searchEngine": "invalid-value",
        })
        self.assertFalse(settings["webSuggestions"])
        self.assertEqual(settings["maxApps"], 24)
        self.assertEqual(settings["maxSuggestions"], 0)
        self.assertEqual(settings["maxResults"], 50)
        self.assertFalse(settings["learningEnabled"])
        self.assertEqual(settings["searchEngine"], "g")

    def test_file_reader_rejects_symlinks_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "target").write_bytes(b"secret")
            (base / "link").symlink_to("target")
            (base / "large").write_bytes(b"x" * 9)
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(HELPER.Denied):
                    HELPER.read_file(fd, "link", 64)
                with self.assertRaises(HELPER.Denied):
                    HELPER.read_file(fd, "large", 8)
            finally:
                os.close(fd)

    def _run_cmd_files(self, lines_bytes):
        original = HELPER.run_bounded
        HELPER.run_bounded = lambda argv, cap, deadline: (lines_bytes, False)
        try:
            with tempfile.TemporaryDirectory() as directory:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    HELPER.cmd_files([directory, "Downloads"])
        finally:
            HELPER.run_bounded = original
        return buf.getvalue()

    def _assert_payload_fits_qml(self, payload):
        # Spotlight.qml checks `text.length` - JS counts UTF-16 code units,
        # not code points, so a character outside the BMP counts twice
        # there and once under Python's len(). This is the metric that
        # actually has to stay under maxHelperPayloadChars (524288); a
        # Python-len() check alone would pass on exactly the inputs that
        # break it.
        utf16_units = len(payload.encode("utf-16-le")) // 2
        self.assertLess(utf16_units, 524288)
        parsed = json.loads(payload)
        self.assertTrue(parsed["ok"])
        self.assertGreater(len(parsed["files"]), 0)
        return parsed

    def test_files_json_stays_under_the_qml_payload_ceiling_on_long_paths(self):
        # Each row repeats its path across path/name/dir, so a pool of long
        # real-world paths can clear that ceiling well before FILES_COUNT
        # does - this is what used to make loadFiles silently fall back to
        # an empty list.
        long_lines = "\n".join(
            "/home/user/" + "x" * 580 + "-Downloads-%04d" % i for i in range(400)
        ).encode("utf-8") + b"\n"
        parsed = self._assert_payload_fits_qml(self._run_cmd_files(long_lines))
        self.assertLess(len(parsed["files"]), 400)

    def test_files_json_stays_under_the_qml_payload_ceiling_with_json_escapes(self):
        # Control characters are legal in a Linux filename and cmd_files
        # does not reject them, but each one expands to a 6-char \\uXXXX
        # escape in JSON regardless of ensure_ascii - a budget estimated
        # from raw string length, rather than the real serialized size,
        # undercounts this by up to 6x and can still overflow the ceiling.
        control_component = ("a\x01" * 100)
        line = (
            "/home/user/" + "/".join([control_component] * 3) + "/Downloads%04d"
        )
        long_lines = "\n".join(line % i for i in range(400)).encode("utf-8") + b"\n"
        self._assert_payload_fits_qml(self._run_cmd_files(long_lines))

    def test_files_json_stays_under_the_qml_payload_ceiling_with_non_bmp_paths(self):
        # Non-BMP characters (outside U+0000-U+FFFF, e.g. most emoji) are
        # exactly the case where Python len() and JS String.length diverge -
        # this is what the 2x margin in FILES_JSON_BUDGET_CHARS is for. The
        # component is sized close to FILES_PATH_CHARS so the *budget* is
        # what stops row-building here, not FILES_COUNT - a short component
        # would let all 400 rows through under either cutoff and never
        # actually exercise the margin this test exists to protect.
        emoji_component = "\U0001F600" * 450  # U+1F600, outside the BMP
        line = "/home/user/" + emoji_component + "/Downloads%04d"
        long_lines = "\n".join(line % i for i in range(400)).encode("utf-8") + b"\n"
        parsed = self._assert_payload_fits_qml(self._run_cmd_files(long_lines))
        self.assertLess(len(parsed["files"]), 400)

    def test_files_truncated_output_drops_the_last_line(self):
        original = HELPER.run_bounded
        # A path that would otherwise parse as a perfectly normal hit - the
        # point is that `truncated=True` alone is enough to drop it, since a
        # cut mid-path is indistinguishable from a clean one from here.
        HELPER.run_bounded = lambda argv, cap, deadline: (
            b"/home/user/real-hit\n/home/user/maybe-cut-off",
            True,
        )
        try:
            with tempfile.TemporaryDirectory() as directory:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    HELPER.cmd_files([directory, "hit"])
        finally:
            HELPER.run_bounded = original

        parsed = json.loads(buf.getvalue())
        paths = [f["path"] for f in parsed["files"]]
        self.assertIn("/home/user/real-hit", paths)
        self.assertNotIn("/home/user/maybe-cut-off", paths)

    def test_file_results_carry_sha256_path_fingerprints(self):
        parsed = json.loads(self._run_cmd_files(b"/home/user/report.txt\n"))
        self.assertEqual(
            parsed["files"][0]["id"],
            hashlib.sha256(b"/home/user/report.txt").hexdigest(),
        )

    def test_deadline_reaps_the_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "child.pid"
            code = (
                "import os,subprocess,sys,time; "
                "child=subprocess.Popen(['sleep','60']); "
                "open(sys.argv[1],'w').write(str(child.pid)); "
                "print('ready',flush=True); time.sleep(60)"
            )
            output, truncated = HELPER.run_bounded(
                [sys.executable, "-c", code, str(pid_file)], 1024, 0.2
            )
            self.assertTrue(truncated)
            self.assertIn(b"ready", output)
            child_pid = int(pid_file.read_text())
            for _ in range(50):
                if not Path("/proc") .joinpath(str(child_pid)).exists():
                    break
                time.sleep(0.02)
            self.assertFalse(Path("/proc").joinpath(str(child_pid)).exists())

    def test_clean_home_reads_stock_defaults_and_empty_clipboard(self):
        with tempfile.TemporaryDirectory() as directory:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = directory
            try:
                for command, key in ((HELPER.cmd_read_settings, "settings"),
                                     (HELPER.cmd_read_clipboard, "items")):
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        command()
                    reply = json.loads(buf.getvalue())
                    self.assertTrue(reply["ok"])
                    self.assertTrue(reply[key] == [] if key == "items" else reply[key]["fileSearchAlways"])
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_unavailable_web_suggestions_return_an_empty_result(self):
        buf = io.StringIO()
        with mock.patch("urllib.request.build_opener", side_effect=OSError("offline")):
            with contextlib.redirect_stdout(buf):
                HELPER.cmd_suggest(["firefox"])
        self.assertEqual(json.loads(buf.getvalue())["suggestions"], [])

    def test_settings_creation_is_private_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = directory
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    HELPER.cmd_ensure_settings()
                settings = Path(directory) / ".config" / "omarchy" / "spotlight.json"
                self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o600)
                parsed = json.loads(settings.read_text())
                self.assertEqual(parsed["maxResults"], 20)
                settings.write_text('{"custom":true}\n')
                with contextlib.redirect_stdout(io.StringIO()):
                    HELPER.cmd_ensure_settings()
                self.assertEqual(settings.read_text(), '{"custom":true}\n')
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_reset_deletes_only_spotlight_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = directory
            try:
                state = Path(directory) / ".local" / "state" / "omarchy"
                state.mkdir(parents=True)
                usage = state / "spotlight-usage.json"
                other = state / "clipboard-history.json"
                usage.write_text("{}")
                other.write_text("[]")
                with contextlib.redirect_stdout(io.StringIO()):
                    HELPER.cmd_reset_usage()
                self.assertFalse(usage.exists())
                self.assertTrue(other.exists())
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_v1_usage_migrates_to_versioned_v2_ids(self):
        usage = HELPER.normalize_usage({
            "app:firefox": {"count": 2, "last": 10},
            "cmd:theme.pick": {"count": 3, "last": 20},
            "bang.gh": {"count": 4, "last": 30},
        })
        self.assertEqual(usage["version"], 2)
        self.assertEqual(usage["items"]["app:firefox"]["count"], 2)
        self.assertEqual(usage["items"]["action:theme.pick"]["count"], 3)
        self.assertNotIn("bang.gh", usage["items"])
        self.assertEqual(usage["contexts"], {})

    def test_path_fingerprints_are_stable_and_file_metadata_is_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.txt"
            path.write_text("report")
            fingerprint = HELPER.path_fingerprint(str(path))
            self.assertEqual(fingerprint, HELPER.path_fingerprint(str(path)))
            self.assertEqual(fingerprint, hashlib.sha256(str(path).encode()).hexdigest())
            self.assertEqual(len(fingerprint), 64)

            usage = HELPER.normalize_usage({
                "version": 2,
                "items": {
                    "file:" + fingerprint: {
                        "count": 1, "last": 1, "meta": {"path": str(path)}
                    },
                    "file:" + "0" * 64: {
                        "count": 1, "last": 1, "meta": {"path": str(path)}
                    },
                },
                "contexts": {},
            })
            self.assertIn("file:" + fingerprint, usage["items"])
            self.assertNotIn("file:" + "0" * 64, usage["items"])

    def test_v2_usage_enforces_all_count_and_byte_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            items = {
                "app:%d" % i: {"count": 1, "last": i}
                for i in range(320)
            }
            file_ids = []
            for i in range(105):
                path = base / ("file-%03d" % i)
                path.touch()
                item_id = "file:" + HELPER.path_fingerprint(str(path))
                file_ids.append(item_id)
                items[item_id] = {
                    "count": 1, "last": i, "meta": {"path": str(path)}
                }
            contexts = {}
            for i in range(140):
                contexts["query:q%d" % i] = {
                    "app:%d" % hit: {"count": 1, "last": i}
                    for hit in range(10)
                }

            usage = HELPER.normalize_usage({
                "version": 2, "items": items, "contexts": contexts
            })
            self.assertLessEqual(len(usage["items"]), 400)
            self.assertLessEqual(
                sum(item_id.startswith("file:") for item_id in usage["items"]), 100
            )
            self.assertLessEqual(len(usage["contexts"]), 128)
            self.assertTrue(all(len(hits) <= 8 for hits in usage["contexts"].values()))
            payload = json.dumps(usage, ensure_ascii=False, separators=(",", ":")).encode()
            self.assertLessEqual(len(payload), HELPER.USAGE_JSON_BUDGET_BYTES)

    def test_missing_usage_file_returns_an_empty_v2_store(self):
        with tempfile.TemporaryDirectory() as directory:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = directory
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    HELPER.cmd_read_usage()
                usage = json.loads(buf.getvalue())["usage"]
                self.assertEqual(usage, {"version": 2, "items": {}, "contexts": {}})
                self.assertFalse(
                    (Path(directory) / ".local" / "state" / "omarchy" / "spotlight-usage.json").exists()
                )
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

    def test_read_usage_persists_v1_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = directory
            try:
                state = Path(directory) / ".local" / "state" / "omarchy"
                state.mkdir(parents=True)
                path = state / "spotlight-usage.json"
                path.write_text(json.dumps({"app:firefox": {"count": 2, "last": 10}}))
                with contextlib.redirect_stdout(io.StringIO()):
                    HELPER.cmd_read_usage()
                persisted = json.loads(path.read_text())
                self.assertEqual(persisted["version"], 2)
                self.assertEqual(persisted["items"]["app:firefox"]["count"], 2)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home


class MenuCommandsTests(unittest.TestCase):
    MENU_FIXTURE = {
        "root": {"label": "Go"},
        "learn": {"label": "Learn", "parent": "root"},
        "learn.safe": {
            "label": "Safe command",
            "parent": "learn",
            "aliases": ["safe", "fixture"],
            "action": "omarchy-safe --flag",
        },
        "learn.keybindings": {"label": "Keybindings", "action": "omarchy-menu-keybindings"},
        "trigger.toggle.screensaver": {"label": "Screensaver", "action": "omarchy-toggle-screensaver"},
        "setup.keybindings": {"label": "Keybindings", "action": "omarchy-edit-keybindings"},
        "install.example": {"label": "Install", "action": "omarchy-install-example"},
        "remove.example": {"label": "Remove", "action": "omarchy-remove-example"},
        "system.example": {"label": "System", "action": "omarchy-system-example"},
        "external": {"label": "External", "action": "systemctl reboot"},
    }

    def _fixture_menu_commands(self, user_raw=b"{}", default_raw=None):
        original_default = HELPER._menu_read_default
        original_user = HELPER._menu_read_user
        if default_raw is None:
            default_raw = json.dumps({"items": self.MENU_FIXTURE}).encode()
        HELPER._menu_read_default = lambda: default_raw
        HELPER._menu_read_user = lambda: user_raw
        try:
            return HELPER._menu_commands()
        finally:
            HELPER._menu_read_default = original_default
            HELPER._menu_read_user = original_user

    def test_action_resolves_to_argv_for_plain_commands(self):
        self.assertEqual(
            HELPER._menu_resolve_argv("omarchy-launch-webapp 'https://example.com/'"),
            ["omarchy-launch-webapp", "https://example.com/"],
        )

    def test_action_expands_home_and_tilde_without_a_shell(self):
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = "/home/test-user"
        try:
            self.assertEqual(
                HELPER._menu_resolve_argv('omarchy-launch-config-editor "$HOME/.config/hypr/hyprland.lua"'),
                ["omarchy-launch-config-editor", "/home/test-user/.config/hypr/hyprland.lua"],
            )
            self.assertEqual(
                HELPER._menu_resolve_argv("omarchy-launch-config-editor ~/.XCompose"),
                ["omarchy-launch-config-editor", "/home/test-user/.XCompose"],
            )
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_action_needing_a_real_shell_is_rejected_not_reinterpreted(self):
        # Real entries from the shipped menu tree - each needs actual shell
        # semantics (||, &&, command substitution, if/then) that shlex does
        # not provide, so none of them may become an argv vector.
        for action in (
            "pkill hyprpicker || hyprpicker -a",
            'theme=$(omarchy-theme-switcher); [[ -n $theme ]] && omarchy-theme-set "$theme"',
            "omarchy-launch-config-editor ~/.config/hypr/hyprsunset.conf && omarchy-restart-hyprsunset",
            "if omarchy-cmd-present nvidia-smi; then ollama_pkg=ollama-cuda; fi",
        ):
            self.assertIsNone(HELPER._menu_resolve_argv(action), action)

    def test_action_with_an_unresolved_variable_is_rejected(self):
        # $HOME/~ are the only substitutions this ever performs; anything
        # else left in a token after that is a sign of an expansion this
        # does not understand, not something to pass through literally.
        self.assertIsNone(HELPER._menu_resolve_argv("omarchy-dns $CUSTOM_DNS"))

    def test_action_does_not_expand_a_variable_that_merely_starts_with_home(self):
        # $HOMEDIR is a different variable that happens to start with the
        # same four letters - a substring replace turned it into a
        # fabricated path instead of leaving it as the unresolved variable
        # it is, which the token-with-a-$-left-in-it check rejects.
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = "/home/test-user"
        try:
            self.assertIsNone(HELPER._menu_resolve_argv("omarchy-launch-config-editor $HOMEDIR/a"))
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_action_with_a_single_quoted_home_stays_literal_not_expanded(self):
        # Single quotes in real Bash mean literal - $HOME under them is
        # never a variable reference, so the correct argv value is the
        # literal string "$HOME/a", not an expanded path and not a
        # rejection (this is now resolvable exactly, not just detectable
        # as wrong - see the quote-aware tokeniser).
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = "/home/test-user"
        try:
            self.assertEqual(
                HELPER._menu_resolve_argv("omarchy-launch-config-editor '$HOME/a'"),
                ["omarchy-launch-config-editor", "$HOME/a"],
            )
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_action_with_a_quote_concatenation_trick_stays_literal(self):
        # Bash joins an adjacent quoted and unquoted span into one token
        # with no whitespace between them, so `'$'HOME/a` - a single-quoted
        # literal `$` immediately followed by unquoted `HOME/a` - is the
        # literal string "$HOME/a", never an expansion of $HOME: only the
        # `$` itself was ever quoted, and unquoted `HOME/a` has no `$` in
        # it to expand. Found by review: a check that only asks "is the
        # whole $HOME substring inside quotes" cannot see this, since no
        # quote in the source spans all of "$HOME".
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = "/home/test-user"
        try:
            for action in (
                "omarchy-launch-config-editor '$'HOME/a",
                'omarchy-launch-config-editor "$"HOME/a',
            ):
                self.assertEqual(
                    HELPER._menu_resolve_argv(action),
                    ["omarchy-launch-config-editor", "$HOME/a"],
                    action,
                )
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_action_keeps_shell_metacharacters_literal_inside_quotes(self):
        # ?, &, *, {}, [] only mean anything to a real shell when they are
        # not quoted - found by review, rejecting them unconditionally (a
        # regex over the raw string before tokenising) made a harmless,
        # already-quoted URL query string vanish from the catalogue, the
        # same false-negative failure this module otherwise avoids on
        # purpose. omarchy-launch-webapp with a quoted URL is a real,
        # common shape in the shipped tree.
        self.assertEqual(
            HELPER._menu_resolve_argv("omarchy-launch-webapp 'https://x.com/?a=1&b=2'"),
            ["omarchy-launch-webapp", "https://x.com/?a=1&b=2"],
        )
        self.assertEqual(
            HELPER._menu_resolve_argv("omarchy-foo 'file * name'"),
            ["omarchy-foo", "file * name"],
        )

    def test_action_tilde_expansion_respects_real_token_boundaries(self):
        # Found by review: a regex checking "is there a ~ somewhere between
        # a pair of quotes" could match across two separate quoted tokens
        # rather than within one, falsely treating an unquoted ~ in between
        # as though it were quoted. A real per-character tokeniser cannot
        # make that mistake.
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = "/home/test-user"
        try:
            self.assertEqual(
                HELPER._menu_resolve_argv("omarchy-foo 'a' ~/x 'b'"),
                ["omarchy-foo", "a", "/home/test-user/x", "b"],
            )
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_action_rejects_redirection_background_and_glob_operators(self):
        # Real evidence from the review: shlex tokenises these into
        # syntactically valid-looking argv (">"/"&" as literal tokens)
        # instead of raising, so the operator blacklist - not shlex itself -
        # is what has to catch them.
        for action in (
            "omarchy-dns DHCP > /tmp/dns.log",
            "omarchy-dns DHCP 2> /tmp/dns.log",
            "omarchy-dns DHCP < /tmp/in",
            "omarchy-dns DHCP &",
            "omarchy-launch-webapp *.desktop",
            "omarchy-launch-webapp {a,b}",
            "omarchy-probe (a)",
            "omarchy-probe a)",
        ):
            self.assertIsNone(HELPER._menu_resolve_argv(action), action)

    def test_action_rejects_nonleading_unquoted_tilde(self):
        # Bash expands ~ after the `=`/`:` in assignment-shaped words, but
        # this lexer deliberately does not implement the complete assignment
        # grammar. Passing it through literally would execute a different
        # argv, so ambiguous non-leading unquoted forms fail closed. A quoted
        # tilde is unambiguously literal and remains supported.
        for action in (
            "omarchy-probe x=~/foo",
            "omarchy-probe x=a:~/foo",
            "omarchy-probe foo~bar",
        ):
            self.assertIsNone(HELPER._menu_resolve_argv(action), action)
        self.assertEqual(
            HELPER._menu_resolve_argv("omarchy-probe 'x=~/foo'"),
            ["omarchy-probe", "x=~/foo"],
        )

    def test_action_rejects_an_unquoted_newline_as_a_command_separator(self):
        # Found by review: \n is whitespace to Python's isspace() but a
        # command separator to real Bash, not a word separator - two lines
        # are two commands, never one command with an extra argument. This
        # is the exact failure that reproved the very first review round;
        # a lexer rewrite reintroduced it by checking isspace() before the
        # reject-char set that already listed \n.
        self.assertIsNone(HELPER._menu_resolve_argv("omarchy-a\nomarchy-b"))

    def test_action_rejects_named_and_special_tilde_forms(self):
        # Only `~` alone and `~/...` are ever expanded - found by review,
        # expanding any leading ~ unconditionally fabricated a path for
        # `~user` (another user's home directory), `~+` ($PWD) and `~-`
        # ($OLDPWD), none of which this module can resolve correctly
        # without guessing.
        for action in ("omarchy-probe ~foo", "omarchy-probe ~foo/bar", "omarchy-probe ~+", "omarchy-probe ~-"):
            self.assertIsNone(HELPER._menu_resolve_argv(action), action)
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = "/home/test-user"
        try:
            self.assertEqual(HELPER._menu_resolve_argv("omarchy-probe ~"), ["omarchy-probe", "/home/test-user"])
            self.assertEqual(HELPER._menu_resolve_argv("omarchy-probe ~/x"), ["omarchy-probe", "/home/test-user/x"])
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    def test_action_keeps_an_explicit_empty_quoted_argument(self):
        # Found by review: '' and "" are legitimate empty arguments in real
        # Bash, not nothing - dropping them shifts every positional
        # argument after it, silently calling the command with the wrong
        # arity.
        self.assertEqual(HELPER._menu_resolve_argv("omarchy-probe '' tail"), ["omarchy-probe", "", "tail"])
        self.assertEqual(HELPER._menu_resolve_argv('omarchy-probe ""'), ["omarchy-probe", ""])

    def test_action_rejects_ansi_c_and_locale_quoting(self):
        # Found by review: $'...' (ANSI-C quoting) and $"..." (locale
        # quoting) are real Bash constructs this module does not
        # implement. Treating the $ as a literal dollar sign here (as it
        # correctly is inside already-open double quotes, where a lone '
        # has no special meaning) accepted the action with the wrong
        # argument - $'abc' means the single argument "abc" in Bash, not a
        # literal "$" followed by a separately-quoted "abc".
        self.assertIsNone(HELPER._menu_resolve_argv("omarchy-probe $'abc'"))
        self.assertIsNone(HELPER._menu_resolve_argv('omarchy-probe $"abc"'))

    def test_action_keeps_carriage_return_vtab_formfeed_literal_in_a_word(self):
        # Found by review: Python's str.isspace() is true for \r/\v/\f too,
        # but Bash's default IFS is only space/tab/newline - those three
        # are ordinary characters *inside* a Bash word, not separators.
        # Splitting a word on them shifted positional arguments, the same
        # class of bug as newline being consumed by isspace() before the
        # reject check could see it, just narrower in practice.
        self.assertEqual(HELPER._menu_resolve_argv("omarchy-probe a\rb"), ["omarchy-probe", "a\rb"])
        self.assertEqual(HELPER._menu_resolve_argv("omarchy-probe a\vb"), ["omarchy-probe", "a\vb"])
        self.assertEqual(HELPER._menu_resolve_argv("omarchy-probe a\fb"), ["omarchy-probe", "a\fb"])

    def test_systemctl_action_is_rejected_regardless_of_shape(self):
        # The exact case Commands.js already refuses by hand (its own
        # comment: a bare systemctl call costs the marketplace listing its
        # automatic Verified status) - argv-clean, two tokens, no shell
        # operator at all, and still must not pass the argv[0] gate.
        self.assertIsNone(HELPER._menu_resolve_argv("systemctl suspend"))
        self.assertIsNone(HELPER._menu_resolve_argv("systemctl hibernate"))

    def test_action_is_capped_on_token_count_and_token_length(self):
        many_tokens = "omarchy-launch-webapp " + " ".join("a" for _ in range(HELPER.MENU_ARGV_TOKENS + 1))
        self.assertIsNone(HELPER._menu_resolve_argv(many_tokens))
        long_token = "omarchy-launch-webapp " + ("x" * (HELPER.MENU_ARGV_CHARS + 1))
        self.assertIsNone(HELPER._menu_resolve_argv(long_token))

    def test_when_with_no_condition_allows(self):
        self.assertTrue(HELPER._menu_when_allows(""))
        self.assertTrue(HELPER._menu_when_allows(None))

    def test_when_pkg_present_reads_the_cached_package_list(self):
        original = HELPER._INSTALLED_PACKAGES
        HELPER._INSTALLED_PACKAGES = frozenset({"git", "python"})
        try:
            self.assertTrue(HELPER._menu_when_allows("omarchy-pkg-present git"))
            self.assertFalse(HELPER._menu_when_allows("omarchy-pkg-present nonexistent-pkg"))
            self.assertFalse(HELPER._menu_when_allows("! omarchy-pkg-present git"))
            self.assertTrue(HELPER._menu_when_allows("! omarchy-pkg-present nonexistent-pkg"))
        finally:
            HELPER._INSTALLED_PACKAGES = original

    def test_when_pkg_present_shows_rather_than_hides_on_a_truncated_listing(self):
        # None now distinctly means "truncated/unknown", not "not yet read"
        # (that is the "unread" sentinel) - a truncated pacman -Qq listing
        # must not read as "package absent" for a plain check, nor as
        # "package present" for a negated one; both must default to shown.
        original = HELPER._INSTALLED_PACKAGES
        HELPER._INSTALLED_PACKAGES = None
        try:
            self.assertTrue(HELPER._menu_when_allows("omarchy-pkg-present git"))
            self.assertTrue(HELPER._menu_when_allows("! omarchy-pkg-present git"))
        finally:
            HELPER._INSTALLED_PACKAGES = original

    def test_when_cmd_present_checks_path(self):
        self.assertTrue(HELPER._menu_when_allows("omarchy-cmd-present sh"))
        self.assertFalse(HELPER._menu_when_allows("omarchy-cmd-present definitely-not-a-real-command-xyz"))
        self.assertTrue(HELPER._menu_when_allows("! omarchy-cmd-present definitely-not-a-real-command-xyz"))

    def test_when_path_exists_checks_dir_and_file(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "marker"
            file_path.write_text("x")
            self.assertTrue(HELPER._menu_when_allows("[[ -d %s ]]" % directory))
            self.assertFalse(HELPER._menu_when_allows("[[ ! -d %s ]]" % directory))
            self.assertTrue(HELPER._menu_when_allows("[[ -f %s ]]" % file_path))
            self.assertFalse(HELPER._menu_when_allows("[[ -f %s/missing ]]" % directory))

    def test_when_path_respects_quote_type_for_home_and_tilde_expansion(self):
        # Found by review: $HOME expands inside double quotes and unquoted
        # text (real Bash's rule) but never inside single quotes; ~ never
        # expands under any quoting. A literal directory named "$HOME" or
        # "~" almost certainly does not exist, so the un-negated condition
        # is False and the negated one True - if either got expanded, the
        # real home directory (which does exist) would flip both results.
        self.assertFalse(HELPER._menu_when_allows("[[ -d '$HOME' ]]"))
        self.assertTrue(HELPER._menu_when_allows("[[ ! -d '$HOME' ]]"))
        self.assertFalse(HELPER._menu_when_allows('[[ -d "~" ]]'))
        self.assertTrue(HELPER._menu_when_allows('[[ ! -d "~" ]]'))
        # Unquoted and double-quoted $HOME still expand correctly.
        home = os.environ.get("HOME", "")
        if home:
            self.assertTrue(HELPER._menu_when_allows("[[ -d %s ]]" % home))
            self.assertTrue(HELPER._menu_when_allows('[[ -d "$HOME" ]]'))

    def test_when_path_exists_handles_quoted_paths_with_spaces(self):
        # A quoted path is the normal, equivalent Bash form - the previous
        # regex captured the quotes themselves as part of the filename, so
        # `[[ -d "/" ]]` came back False even though `/` plainly exists.
        self.assertTrue(HELPER._menu_when_allows('[[ -d "/" ]]'))
        self.assertTrue(HELPER._menu_when_allows("[[ -d '/' ]]"))
        with tempfile.TemporaryDirectory() as directory:
            spaced = Path(directory) / "Xbox Cloud Gaming"
            spaced.mkdir()
            self.assertTrue(HELPER._menu_when_allows('[[ -d "%s" ]]' % spaced))
            self.assertFalse(HELPER._menu_when_allows('[[ -d "%s missing" ]]' % spaced))

    def test_when_unrecognised_condition_shows_rather_than_hides(self):
        # A false negative (a row silently disappears) is worse in a
        # launcher than a false positive (one dead row for hardware the
        # user does not have), so anything this cannot answer defaults to
        # visible.
        self.assertTrue(HELPER._menu_when_allows("omarchy-hw-dell-xps-haptic-touchpad"))
        self.assertTrue(HELPER._menu_when_allows("[[ $(findmnt -no FSTYPE /) == btrfs ]]"))

    def test_merge_overrides_fields_not_whole_entries(self):
        default_items = {"personal": {"label": "Personal", "icon": "A", "action": "omarchy-x"}}
        user_items = {"personal": {"label": "Mine"}}
        merged, order = HELPER._menu_merge(default_items, user_items)
        self.assertEqual(order, ["personal"])
        self.assertEqual(merged["personal"]["label"], "Mine")
        self.assertEqual(merged["personal"]["icon"], "A")
        self.assertEqual(merged["personal"]["action"], "omarchy-x")

    def test_merge_does_not_leave_a_stale_action_when_an_extension_turns_it_into_a_link(self):
        # The review's main finding: merging raw dicts (rather than
        # normalizing each source first, as the real MenuModel.js does)
        # let a default action survive under an extension's replacement
        # label even though the extension itself no longer sets `action`
        # at all - the exact case where the real menu runs nothing and
        # Spotlight would otherwise have kept running the old command.
        default_items = HELPER._menu_parse_items(
            json.dumps({"custom": {"label": "Original", "action": "omarchy-x"}}).encode()
        )
        user_items = HELPER._menu_parse_items(
            json.dumps({"custom": {"label": "Submenu", "target": "style"}}).encode()
        )
        merged, order = HELPER._menu_merge(default_items, user_items)
        self.assertEqual(merged["custom"]["kind"], "link")
        self.assertEqual(merged["custom"]["action"], "")
        self.assertEqual(merged["custom"]["target"], "style")

    def test_breadcrumb_walks_labelled_ancestors_and_tolerates_cycles(self):
        merged = {
            "a": {"label": "Top", "parent": "root"},
            "a.b": {"label": "Mid", "parent": "a"},
            "a.b.c": {"label": "Leaf", "parent": "a.b"},
        }
        self.assertEqual(HELPER._menu_breadcrumb("a.b.c", merged), "Top › Mid")

        cyclic = {
            "x": {"label": "X", "parent": "y"},
            "y": {"label": "Y", "parent": "x"},
        }
        # Must terminate rather than loop forever; the exact crumb does not
        # matter as much as returning at all.
        HELPER._menu_breadcrumb("x", cyclic)

    def test_breadcrumb_clamps_each_ancestor_label(self):
        merged = {
            "a": {"label": "x" * (HELPER.MENU_BREADCRUMB_LABEL_CHARS + 50), "parent": "root"},
            "a.b": {"label": "Leaf", "parent": "a"},
        }
        crumb = HELPER._menu_breadcrumb("a.b", merged)
        self.assertLessEqual(len(crumb), HELPER.MENU_BREADCRUMB_LABEL_CHARS + 3)

    def test_menu_commands_never_emit_a_non_omarchy_prefixed_command(self):
        for row in self._fixture_menu_commands():
            self.assertTrue(row["argv"][0].startswith("omarchy-"), row)

    def test_menu_commands_exclude_install_remove_and_system_subtrees(self):
        for row in self._fixture_menu_commands():
            item_id = row["key"].split(":", 1)[1]
            self.assertFalse(item_id.startswith(("install.", "remove.", "system.")), item_id)
            self.assertNotIn(item_id, ("install", "remove", "system"))

    def test_menu_commands_exclude_ids_that_collide_with_commands_js(self):
        # Keybindings and Screensaver already exist by hand in Commands.js
        # with different (Screensaver: opposite) behaviour - a second,
        # differently-behaving row under the same title is a worse outcome
        # than the menu tree's copy being absent from this catalogue.
        #
        # Found by review: asserting id-not-in-emitted-set against
        # MENU_SKIP_IDS itself is a tautology for a typo'd id (it can never
        # appear, whether the skip worked or the id was simply never real),
        # so this checks the actual property that matters - no title this
        # module emits collides with one of Commands.js's curated titles -
        # rather than trusting the skip list to grade its own homework.
        commands_js_titles = {"Keybindings", "Screensaver"}
        for row in self._fixture_menu_commands():
            self.assertNotIn(row["title"], commands_js_titles, row)

    def test_menu_commands_stops_before_exceeding_the_json_budget(self):
        # Row count and per-label clamps alone do not bound the real
        # serialized payload; MENU_JSON_BUDGET_CHARS is the defense-in-depth
        # that actually has to trip. Shrink the budget rather than trying to
        # organically produce >200000 chars, so the assertion is exact and
        # not dependent on today's field-length constants.
        original_default = HELPER._menu_read_default
        original_user = HELPER._menu_read_user
        original_budget = HELPER.MENU_JSON_BUDGET_CHARS
        tree = {}
        for i in range(60):
            tree["c%d" % i] = {"label": "Leaf number %d" % i, "action": "omarchy-x"}
        HELPER._menu_read_default = lambda: json.dumps(tree).encode()
        HELPER._menu_read_user = lambda: b"{}"
        HELPER.MENU_JSON_BUDGET_CHARS = 1000
        try:
            rows = HELPER._menu_commands()
            self.assertGreater(len(rows), 0)
            self.assertLess(len(rows), 60)
            total = len(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
            self.assertLessEqual(total, HELPER.MENU_JSON_BUDGET_CHARS + 200)
        finally:
            HELPER._menu_read_default = original_default
            HELPER._menu_read_user = original_user
            HELPER.MENU_JSON_BUDGET_CHARS = original_budget

    def test_menu_commands_always_emits_at_least_one_row_even_over_budget(self):
        # A single row larger than the whole budget must still go out - the
        # budget check only applies once at least one row has been emitted,
        # so one oversized entry cannot silently empty the entire catalogue.
        original_default = HELPER._menu_read_default
        original_user = HELPER._menu_read_user
        original_budget = HELPER.MENU_JSON_BUDGET_CHARS
        HELPER._menu_read_default = lambda: json.dumps(
            {"only": {"label": "Only Item", "action": "omarchy-x"}}
        ).encode()
        HELPER._menu_read_user = lambda: b"{}"
        HELPER.MENU_JSON_BUDGET_CHARS = 1
        try:
            rows = HELPER._menu_commands()
            self.assertEqual(len(rows), 1)
        finally:
            HELPER._menu_read_default = original_default
            HELPER._menu_read_user = original_user
            HELPER.MENU_JSON_BUDGET_CHARS = original_budget

    def test_menu_commands_row_shape_matches_commands_js(self):
        rows = self._fixture_menu_commands()
        self.assertGreater(len(rows), 0)
        for row in rows[:5]:
            self.assertEqual(
                set(row.keys()), {"key", "title", "subtitle", "icon", "argv", "keywords"}
            )
            self.assertIsInstance(row["argv"], list)
            self.assertTrue(row["key"].startswith("menu:"))

    def test_menu_commands_survives_a_missing_or_malformed_user_extension(self):
        rows = self._fixture_menu_commands(b"{ not json at all")
        self.assertGreater(len(rows), 0)

    @unittest.skipUnless(
        Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"), *HELPER.MENU_PARTS, HELPER.MENU_NAME).is_file(),
        "installed Omarchy menu is unavailable",
    )
    def test_installed_menu_matches_projection_safety_invariants(self):
        # Optional integration coverage for Omarchy hosts. Read the fixture
        # directly here so filesystem sandbox UID remapping does not turn a
        # parser/projection test into an ownership-policy test; read_file's
        # ownership checks have their own focused coverage above.
        menu_path = Path(
            os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"),
            *HELPER.MENU_PARTS,
            HELPER.MENU_NAME,
        )
        rows = self._fixture_menu_commands(default_raw=menu_path.read_bytes())
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertTrue(row["argv"][0].startswith("omarchy-"), row)
            item_id = row["key"].split(":", 1)[1]
            self.assertFalse(item_id.startswith(HELPER.MENU_SKIP_PREFIXES), item_id)


@unittest.skipUnless(shutil.which("bash"), "bash not available")
class TokenizeVsBashTests(unittest.TestCase):
    """A compact differential harness against real Bash - not exhaustive,
    but the shape of check that actually caught every defect found across
    review rounds 6-8 (a newline regression, ~user/~+/~- fabrication, a
    dropped empty quoted argument, ANSI-C/locale quoting), none of which an
    inline unit test asserting one input/output pair at a time had managed
    to catch before the bug was already reported by a human reviewer.

    Each action runs for real under `bash -c`, with PATH restricted to a
    directory of shim executables that record their own argv instead of
    doing anything - so nothing real ever executes, and the check is
    self-validating rather than needing a hand-maintained expected-output
    table: if Bash runs the shim exactly once, _menu_resolve_argv must
    return that exact argv; if Bash runs it zero times (a syntax error) or
    more than once (e.g. a newline splitting one action into two
    commands), _menu_resolve_argv must return None, since this module only
    ever accepts an action that is unambiguously one single simple command.
    """

    SHIM_NAMES = ("omarchy-probe", "omarchy-a", "omarchy-b")

    @classmethod
    def setUpClass(cls):
        cls.bash_path = shutil.which("bash")
        cls.shimdir = tempfile.mkdtemp(prefix="menu-tokenize-shim-")
        shim_src = (
            "#!" + sys.executable + "\n"
            "import json, os, sys\n"
            "with open(os.environ['MENU_TOKENIZE_LOG'], 'a') as f:\n"
            "    f.write(json.dumps([os.path.basename(sys.argv[0])] + sys.argv[1:]) + '\\n')\n"
        )
        for name in cls.SHIM_NAMES:
            path = Path(cls.shimdir) / name
            path.write_text(shim_src)
            path.chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.shimdir, ignore_errors=True)

    def _bash_invocations(self, action):
        with tempfile.NamedTemporaryFile(prefix="menu-tokenize-log-", suffix=".jsonl", delete=False) as f:
            logfile = f.name
        try:
            # cwd is a scratch directory, not the repo: a case like "a > b"
            # is meant to be *rejected*, precisely because Bash really
            # would create a file named "b" here - which is exactly what
            # happens when this harness runs the action for real to find
            # out, and it must not land in the repo's own working tree.
            with tempfile.TemporaryDirectory(prefix="menu-tokenize-cwd-") as cwd:
                env = {
                    "PATH": self.shimdir,
                    "HOME": os.environ.get("HOME", "/root"),
                    "MENU_TOKENIZE_LOG": logfile,
                }
                subprocess.run(
                    [self.bash_path, "-c", action],
                    env=env, cwd=cwd, timeout=5,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            lines = Path(logfile).read_text().splitlines()
            return [json.loads(line) for line in lines]
        finally:
            os.unlink(logfile)

    def _assert_agrees_with_bash(self, action):
        # Over-rejecting is always safe here by this module's own explicit
        # policy (unrecognised syntax is excluded, never guessed at), so
        # only one direction is actually a bug: this module accepting an
        # action and resolving it to something other than what Bash itself
        # would run it as. A None result is never asserted against Bash -
        # it is deliberately conservative for several real constructs
        # (~user, for instance) that Bash would run unambiguously.
        invocations = self._bash_invocations(action)
        got = HELPER._menu_resolve_argv(action)
        if got is None:
            return
        self.assertEqual(len(invocations), 1, (action, got, invocations))
        self.assertEqual(got, invocations[0], action)

    def test_agrees_with_bash_across_the_corpus(self):
        cases = [
            "omarchy-probe a b c",
            "omarchy-probe 'a b' c",
            'omarchy-probe "a b" c',
            "omarchy-probe a'b'c",
            "omarchy-probe ~/x",
            "omarchy-probe ~",
            "omarchy-probe ~/",
            "omarchy-probe ~foo",
            "omarchy-probe ~foo/bar",
            "omarchy-probe ~+",
            "omarchy-probe ~-",
            "omarchy-probe '' tail",
            'omarchy-probe ""',
            "omarchy-probe '$'HOME/a",
            'omarchy-probe "$"HOME/a',
            'omarchy-probe "$HOME"x',
            "omarchy-probe 'https://x.com/?a=1&b=2'",
            "omarchy-probe 'file * name'",
            "omarchy-probe a\tb",
            "omarchy-probe a\rb",
            "omarchy-probe a\vb",
            "omarchy-probe a\fb",
            "omarchy-probe $'abc'",
            'omarchy-probe $"abc"',
            "omarchy-probe a$'b'",
            "omarchy-probe $CUSTOM_DNS",
            "omarchy-probe $HOMEDIR/a",
            "omarchy-probe a > b",
            "omarchy-probe a < b",
            # Not "a & b": backgrounding races bash's own exit against the
            # shim's file write, since bash -c does not wait on background
            # jobs before exiting - unreliable to assert here, and the
            # rejection is already pinned deterministically by the plain
            # unit tests above.
            "omarchy-probe a && b",
            "omarchy-probe a || b",
            "omarchy-probe a; b",
            "omarchy-probe *.desktop",
            "omarchy-probe {a,b}",
            "omarchy-probe (a)",
            "omarchy-probe a)",
            "omarchy-probe x=~/foo",
            "omarchy-probe x=a:~/foo",
            "omarchy-a\nomarchy-b",
            "if omarchy-probe x; then omarchy-a; fi",
            "omarchy-probe $(omarchy-a)",
            "omarchy-probe `omarchy-a`",
        ]
        for action in cases:
            self._assert_agrees_with_bash(action)


if __name__ == "__main__":
    unittest.main()
