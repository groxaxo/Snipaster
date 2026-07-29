from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import snipaster_installer


class GVariantParsingTests(unittest.TestCase):
    def test_empty_typed_array(self) -> None:
        self.assertEqual(
            snipaster_installer.parse_gvariant_string_array("@as []"), []
        )

    def test_keybinding_array(self) -> None:
        value = "['/one/', '/two/']"
        self.assertEqual(
            snipaster_installer.parse_gvariant_string_array(value),
            ["/one/", "/two/"],
        )


class XbindkeysMergeTests(unittest.TestCase):
    def test_preserves_user_shortcuts_and_is_idempotent(self) -> None:
        original = '"notify-send existing"\n  Control+F8\n'
        command = "/home/test/.local/bin/snipaster capture"
        once = snipaster_installer.merge_xbindkeys_config(original, command)
        twice = snipaster_installer.merge_xbindkeys_config(once, command)

        self.assertEqual(once, twice)
        self.assertIn("notify-send existing", once)
        self.assertEqual(once.count("Snipaster managed shortcut >>>"), 1)
        self.assertIn(f'"{command}"\n  F1', once)


class UserInstallTests(unittest.TestCase):
    def test_user_level_install_creates_launchers_and_icons(self) -> None:
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            with patch("snipaster_installer.shutil.which", return_value=None):
                result = snipaster_installer.install(
                    progress=lambda _: None,
                    source_dir=source,
                    home=home,
                    install_system_packages=False,
                    launch_tray=False,
                )

            paths = result.paths
            self.assertTrue(paths.launcher.is_file())
            self.assertTrue(os.access(paths.launcher, os.X_OK))
            self.assertTrue(paths.desktop_entry.is_file())
            self.assertTrue(paths.applications_entry.is_file())
            self.assertTrue(paths.icon.is_file())
            self.assertIn(
                '"capture"', paths.desktop_entry.read_text(encoding="utf-8")
            )
            subprocess.run(["sh", "-n", str(paths.launcher)], check=True)
            subprocess.run(
                ["sh", "-n", str(paths.compatibility_launcher)], check=True
            )


if __name__ == "__main__":
    unittest.main()
