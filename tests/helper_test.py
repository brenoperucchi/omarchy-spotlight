import contextlib
import importlib.util
import io
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


if __name__ == "__main__":
    unittest.main()
