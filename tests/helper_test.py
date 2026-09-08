import importlib.util
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


if __name__ == "__main__":
    unittest.main()
