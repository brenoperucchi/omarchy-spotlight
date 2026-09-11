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
        HELPER._INSTALLED_PACKAGES = frozenset({"git", "python"})
        try:
            self.assertTrue(HELPER._menu_when_allows("omarchy-pkg-present git"))
            self.assertFalse(HELPER._menu_when_allows("omarchy-pkg-present nonexistent-pkg"))
            self.assertFalse(HELPER._menu_when_allows("! omarchy-pkg-present git"))
            self.assertTrue(HELPER._menu_when_allows("! omarchy-pkg-present nonexistent-pkg"))
        finally:
            HELPER._INSTALLED_PACKAGES = None

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

    def test_breadcrumb_walks_labelled_ancestors_and_tolerates_cycles(self):
        merged = {
            "a": {"label": "Top", "_parent": "root"},
            "a.b": {"label": "Mid", "_parent": "a"},
            "a.b.c": {"label": "Leaf", "_parent": "a.b"},
        }
        self.assertEqual(HELPER._menu_breadcrumb("a.b.c", merged), "Top › Mid")

        cyclic = {
            "x": {"label": "X", "_parent": "y"},
            "y": {"label": "Y", "_parent": "x"},
        }
        # Must terminate rather than loop forever; the exact crumb does not
        # matter as much as returning at all.
        HELPER._menu_breadcrumb("x", cyclic)

    def test_menu_commands_never_emit_a_non_omarchy_prefixed_command(self):
        for row in HELPER._menu_commands():
            self.assertTrue(row["argv"][0].startswith("omarchy-"), row)

    def test_menu_commands_exclude_install_remove_and_system_subtrees(self):
        for row in HELPER._menu_commands():
            item_id = row["key"].split(":", 1)[1]
            self.assertFalse(item_id.startswith(("install.", "remove.", "system.")), item_id)
            self.assertNotIn(item_id, ("install", "remove", "system"))

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
