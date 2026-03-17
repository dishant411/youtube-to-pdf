from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run_converter


class RunConverterTests(unittest.TestCase):
    def test_detect_mode_for_single_url(self) -> None:
        mode, value = run_converter.detect_mode("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(mode, "single")
        self.assertEqual(value, "https://youtu.be/dQw4w9WgXcQ")

    def test_detect_mode_for_batch_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            batch_file = Path(temp_dir) / "urls.txt"
            batch_file.write_text("https://youtu.be/dQw4w9WgXcQ\n", encoding="utf-8")
            mode, value = run_converter.detect_mode(str(batch_file))
            self.assertEqual(mode, "batch")
            self.assertEqual(value, str(batch_file.resolve()))

    def test_detect_mode_rejects_missing_path_like_value(self) -> None:
        with self.assertRaises(ValueError):
            run_converter.detect_mode("not-a-url-and-not-a-file")

    def test_ensure_docker_available_returns_success_when_present(self) -> None:
        with mock.patch("run_converter.docker_daemon_ready", return_value=True):
            self.assertEqual(run_converter.ensure_docker_available(), (0, False))

    def test_ensure_docker_available_starts_existing_docker_desktop(self) -> None:
        with mock.patch("run_converter.docker_daemon_ready", return_value=False):
            with mock.patch("run_converter.sys.platform", "darwin"):
                with mock.patch("run_converter.docker_runner.resolve_docker_binary", return_value="/usr/local/bin/docker"):
                    with mock.patch("run_converter.start_docker_desktop", return_value=0) as start_docker:
                        self.assertEqual(run_converter.ensure_docker_available(), (0, True))
                        start_docker.assert_called_once_with()

    def test_ensure_docker_available_installs_homebrew_then_docker(self) -> None:
        with mock.patch("run_converter.docker_daemon_ready", return_value=False):
            with mock.patch("run_converter.sys.platform", "darwin"):
                with mock.patch("run_converter.resolve_brew_binary", side_effect=[None, "/opt/homebrew/bin/brew"]):
                    with mock.patch("run_converter.install_homebrew", return_value=0) as install_homebrew:
                        with mock.patch("run_converter.subprocess.run") as run_subprocess:
                            with mock.patch("run_converter.start_docker_desktop", return_value=0):
                                with mock.patch("run_converter.docker_runner.resolve_docker_binary", return_value=None):
                                    run_subprocess.return_value.returncode = 0
                                    self.assertEqual(run_converter.ensure_docker_available(), (0, True))
                                    install_homebrew.assert_called_once_with()
                                    self.assertEqual(
                                        run_subprocess.call_args_list[0].args[0],
                                        ["/opt/homebrew/bin/brew", "install", "--cask", "docker"],
                                    )

    def test_ensure_docker_available_installs_with_brew(self) -> None:
        with mock.patch("run_converter.docker_daemon_ready", return_value=False):
            with mock.patch("run_converter.sys.platform", "darwin"):
                with mock.patch("run_converter.resolve_brew_binary", return_value="/opt/homebrew/bin/brew"):
                    with mock.patch("run_converter.subprocess.run") as run_subprocess:
                        with mock.patch("run_converter.start_docker_desktop", return_value=0):
                            with mock.patch("run_converter.docker_runner.resolve_docker_binary", return_value=None):
                                run_subprocess.return_value.returncode = 0
                                self.assertEqual(run_converter.ensure_docker_available(), (0, True))
                                self.assertEqual(
                                    run_subprocess.call_args_list[0].args[0],
                                    ["/opt/homebrew/bin/brew", "install", "--cask", "docker"],
                                )

    def test_install_homebrew_runs_official_installer(self) -> None:
        fake_response = mock.MagicMock()
        fake_response.__enter__.return_value.read.return_value = b"#!/bin/bash\n"
        with mock.patch("run_converter.urlopen", return_value=fake_response):
            with mock.patch("run_converter.subprocess.run") as run_subprocess:
                run_subprocess.return_value.returncode = 0
                self.assertEqual(run_converter.install_homebrew(), 0)
                self.assertEqual(run_subprocess.call_args[0][0][0], "/bin/bash")

    def test_main_stops_docker_if_wrapper_started_it(self) -> None:
        with mock.patch("run_converter.detect_mode", return_value=("single", "https://youtu.be/dQw4w9WgXcQ")):
            with mock.patch("run_converter.ensure_docker_available", return_value=(0, True)):
                with mock.patch("run_converter.docker_runner.doctor", return_value=0):
                    with mock.patch("run_converter.image_exists", return_value=True):
                        with mock.patch("run_converter.run_conversion", return_value=0):
                            with mock.patch("run_converter.stop_docker_desktop", return_value=0) as stop_docker:
                                self.assertEqual(run_converter.main(["https://youtu.be/dQw4w9WgXcQ"]), 0)
                                stop_docker.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
