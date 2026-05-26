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

    def test_start_docker_desktop_restarts_unhealthy_running_desktop(self) -> None:
        with mock.patch("run_converter.docker_desktop_status", return_value="running"):
            with mock.patch("run_converter.run_docker_desktop_command", return_value=0) as desktop_command:
                with mock.patch("run_converter.wait_for_docker", return_value=0) as wait_for_docker:
                    self.assertEqual(run_converter.start_docker_desktop(), 0)
                    desktop_command.assert_called_once_with("restart")
                    wait_for_docker.assert_called_once_with()

    def test_start_docker_desktop_uses_desktop_cli_before_open_app(self) -> None:
        with mock.patch("run_converter.docker_desktop_status", return_value=None):
            with mock.patch("run_converter.run_docker_desktop_command", return_value=0) as desktop_command:
                with mock.patch("run_converter.wait_for_docker", return_value=0):
                    with mock.patch("run_converter.subprocess.run") as run_subprocess:
                        self.assertEqual(run_converter.start_docker_desktop(), 0)
                        desktop_command.assert_called_once_with("start")
                        run_subprocess.assert_not_called()

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
                            with mock.patch("run_converter._open_macos_outputs"):
                                with mock.patch("run_converter.stop_docker_desktop", return_value=0) as stop_docker:
                                    self.assertEqual(run_converter.main(["https://youtu.be/dQw4w9WgXcQ"]), 0)
                                    stop_docker.assert_called_once_with()

    def test_main_opens_finder_and_new_pdf_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            existing_pdf = output_dir / "existing.pdf"
            new_pdf = output_dir / "new.pdf"
            existing_pdf.write_bytes(b"%PDF-1.4\n")

            def fake_run_conversion(_mode: str, _value: str) -> int:
                new_pdf.write_bytes(b"%PDF-1.4\n")
                return 0

            with mock.patch("run_converter.detect_mode", return_value=("single", "https://youtu.be/dQw4w9WgXcQ")):
                with mock.patch("run_converter.ensure_docker_available", return_value=(0, False)):
                    with mock.patch("run_converter.docker_runner.doctor", return_value=0):
                        with mock.patch("run_converter.image_exists", return_value=True):
                            with mock.patch("run_converter.docker_runner.DEFAULT_OUTPUT_DIR", output_dir):
                                with mock.patch("run_converter.run_conversion", side_effect=fake_run_conversion):
                                    with mock.patch("run_converter._open_macos_outputs") as open_outputs:
                                        self.assertEqual(run_converter.main(["https://youtu.be/dQw4w9WgXcQ"]), 0)
                                        open_outputs.assert_called_once_with(output_dir, [new_pdf.resolve()])

    def test_main_rebuilds_when_image_is_stale(self) -> None:
        with mock.patch("run_converter.detect_mode", return_value=("single", "https://youtu.be/dQw4w9WgXcQ")):
            with mock.patch("run_converter.ensure_docker_available", return_value=(0, False)):
                with mock.patch("run_converter.docker_runner.doctor", return_value=0):
                    with mock.patch("run_converter.image_exists", return_value=True):
                        with mock.patch("run_converter.image_stale", return_value=True):
                            with mock.patch("run_converter.docker_runner.build", return_value=0) as build:
                                with mock.patch("run_converter.run_conversion", return_value=0):
                                    with mock.patch("run_converter._open_macos_outputs"):
                                        self.assertEqual(run_converter.main(["https://youtu.be/dQw4w9WgXcQ"]), 0)
                                        build.assert_called_once_with()

    def test_open_macos_outputs_opens_finder_and_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            pdf_path = output_dir / "new.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")

            with mock.patch("run_converter.sys.platform", "darwin"):
                with mock.patch("run_converter.subprocess.run") as run_subprocess:
                    run_subprocess.return_value.returncode = 0
                    run_converter._open_macos_outputs(output_dir, [pdf_path])

            self.assertEqual(
                [call.args[0] for call in run_subprocess.call_args_list],
                [
                    ["open", str(output_dir)],
                    ["open", "-a", "Preview", str(pdf_path)],
                ],
            )


if __name__ == "__main__":
    unittest.main()
