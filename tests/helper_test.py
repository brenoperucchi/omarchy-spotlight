import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


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

        settings = HELPER.normalize_settings({
            "webSuggestions": "yes",
            "maxApps": 999,
            "maxSuggestions": -5,
            "searchEngine": "invalid-value",
        })
        self.assertFalse(settings["webSuggestions"])
        self.assertEqual(settings["maxApps"], 24)
        self.assertEqual(settings["maxSuggestions"], 0)
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


class MenuCommandsTests(unittest.TestCase):
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
        ):
            self.assertIsNone(HELPER._menu_resolve_argv(action), action)

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
        for row in HELPER._menu_commands():
            self.assertTrue(row["argv"][0].startswith("omarchy-"), row)

    def test_menu_commands_exclude_install_remove_and_system_subtrees(self):
        for row in HELPER._menu_commands():
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
        for row in HELPER._menu_commands():
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
        rows = HELPER._menu_commands()
        self.assertGreater(len(rows), 0)
        for row in rows[:5]:
            self.assertEqual(
                set(row.keys()), {"key", "title", "subtitle", "icon", "argv", "keywords"}
            )
            self.assertIsInstance(row["argv"], list)
            self.assertTrue(row["key"].startswith("menu:"))

    def test_menu_commands_survives_a_missing_or_malformed_user_extension(self):
        original = HELPER._menu_read_user
        HELPER._menu_read_user = lambda: b"{ not json at all"
        try:
            rows = HELPER._menu_commands()
            self.assertGreater(len(rows), 0)
        finally:
            HELPER._menu_read_user = original


if __name__ == "__main__":
    unittest.main()
