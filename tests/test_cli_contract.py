from __future__ import annotations

import io
import tempfile
import unittest
from subprocess import CompletedProcess
from pathlib import Path
from unittest import mock

from app.cli import main
from app.models import TranscriptSegment
from app.openai_summary import SummaryGenerationError
from app.youtube import TranscriptUnavailableError
from scripts import docker_runner


class CliContractTests(unittest.TestCase):
    def test_default_output_dir_points_to_documents(self) -> None:
        self.assertEqual(docker_runner.DEFAULT_OUTPUT_DIR, Path.home() / "Documents" / "youtube-to-pdf")

    def test_single_url_success_writes_summary_pdf_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"

            def fake_render_summary_pdf(output_path, **_kwargs):
                output_path.write_bytes(b"%PDF-1.4\n")

            with mock.patch("app.cli.fetch_transcript_data", return_value=([TranscriptSegment("Hello world.", 0.0, 1.0)], "en")):
                with mock.patch("app.cli.fetch_video_title", return_value="Sample Title"):
                    with mock.patch("app.cli.summarize_transcript", return_value=("## Executive Summary\nHello", "gpt-5.4-nano")):
                        with mock.patch("app.cli.render_summary_pdf", side_effect=fake_render_summary_pdf):
                            exit_code = main(
                                [
                                    "--url",
                                    "https://youtu.be/dQw4w9WgXcQ",
                                    "--output-dir",
                                    str(output_dir),
                                ]
                            )

            self.assertEqual(exit_code, 0)
            output_names = [path.name for path in output_dir.iterdir()]
            self.assertEqual(output_names, ["sample-title.pdf"])

    def test_single_url_transcript_mode_still_writes_legacy_transcript_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"

            def fake_render_pdf(output_path, **_kwargs):
                output_path.write_bytes(b"%PDF-1.4\n")

            with mock.patch("app.cli.fetch_transcript_data", return_value=([TranscriptSegment("Hello world.", 0.0, 1.0)], "en")):
                with mock.patch("app.cli.fetch_video_title", return_value="Sample Title"):
                    with mock.patch("app.cli.render_pdf", side_effect=fake_render_pdf):
                        exit_code = main(
                            [
                                "--url",
                                "https://youtu.be/dQw4w9WgXcQ",
                                "--output-dir",
                                str(output_dir),
                                "--mode",
                                "transcript",
                            ]
                        )

            self.assertEqual(exit_code, 0)
            output_names = [path.name for path in output_dir.iterdir()]
            self.assertEqual(output_names, ["sample-title.pdf"])

    def test_single_url_missing_transcript_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            with mock.patch("app.cli.fetch_transcript_data", side_effect=TranscriptUnavailableError("no transcript")):
                exit_code = main(
                    [
                        "--url",
                        "https://youtu.be/dQw4w9WgXcQ",
                        "--output-dir",
                        str(output_dir),
                    ]
                )
            self.assertEqual(exit_code, 1)
            self.assertEqual(list(output_dir.iterdir()), [])

    def test_single_url_summary_failure_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            with mock.patch("app.cli.fetch_transcript_data", return_value=([TranscriptSegment("Hello world.", 0.0, 1.0)], "en")):
                with mock.patch("app.cli.fetch_video_title", return_value="Sample Title"):
                    with mock.patch("app.cli.summarize_transcript", side_effect=SummaryGenerationError("summary failed")):
                        exit_code = main(
                            [
                                "--url",
                                "https://youtu.be/dQw4w9WgXcQ",
                                "--output-dir",
                                str(output_dir),
                            ]
                        )

            self.assertEqual(exit_code, 1)
            self.assertEqual(list(output_dir.iterdir()), [])

    def test_batch_mode_skips_missing_transcripts_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            batch_file = root / "urls.txt"
            output_dir = root / "out"
            batch_file.write_text(
                "\n".join(
                    [
                        "# comment",
                        "https://youtu.be/dQw4w9WgXcQ",
                        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10",
                        "https://www.youtube.com/watch?v=9bZkp7q19f0",
                    ]
                ),
                encoding="utf-8",
            )

            def fake_fetch(video_id):
                if video_id == "9bZkp7q19f0":
                    raise TranscriptUnavailableError("missing transcript")
                return [TranscriptSegment("Hello", 0.0, 1.0)], "en"

            def fake_render_summary_pdf(output_path, **_kwargs):
                output_path.write_bytes(b"%PDF-1.4\n")

            with mock.patch("app.cli.fetch_transcript_data", side_effect=fake_fetch):
                with mock.patch("app.cli.fetch_video_title", return_value="Batch Title"):
                    with mock.patch("app.cli.summarize_transcript", return_value=("## Executive Summary\nHello", "gpt-5.4-nano")):
                        with mock.patch("app.cli.render_summary_pdf", side_effect=fake_render_summary_pdf):
                            exit_code = main(
                                [
                                    "--batch-file",
                                    str(batch_file),
                                    "--output-dir",
                                    str(output_dir),
                                ]
                            )

            self.assertEqual(exit_code, 0)
            output_names = sorted(path.name for path in output_dir.iterdir())
            self.assertEqual(output_names, ["batch-title.pdf"])

    def test_batch_mode_rejects_missing_batch_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            exit_code = main(
                [
                    "--batch-file",
                    str(Path(temp_dir) / "missing.txt"),
                    "--output-dir",
                    str(output_dir),
                ]
            )
            self.assertEqual(exit_code, 1)
            self.assertEqual(list(output_dir.iterdir()), [])

    def test_duplicate_titles_get_incremented_pdf_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "same-title.pdf").write_bytes(b"existing")

            def fake_render_summary_pdf(output_path, **_kwargs):
                output_path.write_bytes(b"%PDF-1.4\n")

            with mock.patch("app.cli.fetch_transcript_data", return_value=([TranscriptSegment("Hello world.", 0.0, 1.0)], "en")):
                with mock.patch("app.cli.fetch_video_title", return_value="Same Title"):
                    with mock.patch("app.cli.summarize_transcript", return_value=("## Executive Summary\nHello", "gpt-5.4-nano")):
                        with mock.patch("app.cli.render_summary_pdf", side_effect=fake_render_summary_pdf):
                            exit_code = main(
                                [
                                    "--url",
                                    "https://youtu.be/dQw4w9WgXcQ",
                                    "--output-dir",
                                    str(output_dir),
                                ]
                            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "same-title-2.pdf").exists())

    def test_legacy_json_outputs_are_removed_before_new_pdf_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "manifest.json").write_text("{}", encoding="utf-8")
            (output_dir / "old-title.json").write_text("{}", encoding="utf-8")

            def fake_render_summary_pdf(output_path, **_kwargs):
                output_path.write_bytes(b"%PDF-1.4\n")

            with mock.patch("app.cli.fetch_transcript_data", return_value=([TranscriptSegment("Hello world.", 0.0, 1.0)], "en")):
                with mock.patch("app.cli.fetch_video_title", return_value="Fresh Title"):
                    with mock.patch("app.cli.summarize_transcript", return_value=("## Executive Summary\nHello", "gpt-5.4-nano")):
                        with mock.patch("app.cli.render_summary_pdf", side_effect=fake_render_summary_pdf):
                            exit_code = main(
                                [
                                    "--url",
                                    "https://youtu.be/dQw4w9WgXcQ",
                                    "--output-dir",
                                    str(output_dir),
                                ]
                            )

            self.assertEqual(exit_code, 0)
            self.assertFalse((output_dir / "manifest.json").exists())
            self.assertFalse((output_dir / "old-title.json").exists())

    def test_docker_runtime_passes_openai_environment_variables(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            value_file = Path(temp_dir) / "value.txt"
            value_file.write_text("https://youtu.be/dQw4w9WgXcQ", encoding="utf-8")

            with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "your_test_openai_key", "OPENAI_MODEL": "gpt-5.4-nano"}, clear=False):
                with mock.patch("scripts.docker_runner.ensure_output_dir", return_value=Path("/tmp/out")):
                    with mock.patch("scripts.docker_runner.resolve_docker_binary", return_value="/usr/local/bin/docker"):
                        with mock.patch("scripts.docker_runner.image_exists", return_value=True):
                            with mock.patch("scripts.docker_runner.run_subprocess", return_value=0) as run_subprocess:
                                exit_code = docker_runner.main(["run", "--value-file", str(value_file)])

            self.assertEqual(exit_code, 0)
            docker_command = run_subprocess.call_args[0][0]
            self.assertIn("--env", docker_command)
            self.assertIn("OPENAI_API_KEY=your_test_openai_key", docker_command)
            self.assertIn("OPENAI_MODEL=gpt-5.4-nano", docker_command)

    def test_docker_runtime_uses_hardened_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            value_file = Path(temp_dir) / "value.txt"
            value_file.write_text("https://youtu.be/dQw4w9WgXcQ", encoding="utf-8")

            with mock.patch("scripts.docker_runner.ensure_output_dir", return_value=Path("/tmp/out")):
                with mock.patch("scripts.docker_runner.resolve_docker_binary", return_value="/usr/local/bin/docker"):
                    with mock.patch("scripts.docker_runner.image_exists", return_value=True):
                        with mock.patch("scripts.docker_runner.run_subprocess", return_value=0) as run_subprocess:
                            exit_code = docker_runner.main(["run", "--value-file", str(value_file)])

            self.assertEqual(exit_code, 0)
            docker_command = run_subprocess.call_args[0][0]
            self.assertIn("--network=host", docker_command)
            self.assertIn("--read-only", docker_command)
            self.assertIn("--cap-drop=ALL", docker_command)
            self.assertIn("--security-opt=no-new-privileges", docker_command)
            self.assertIn("--tmpfs", docker_command)
            self.assertIn("--user", docker_command)

    def test_docker_run_builds_image_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            value_file = Path(temp_dir) / "value.txt"
            value_file.write_text("https://youtu.be/dQw4w9WgXcQ", encoding="utf-8")

            with mock.patch("scripts.docker_runner.ensure_output_dir", return_value=Path("/tmp/out")):
                with mock.patch("scripts.docker_runner.image_exists", return_value=False):
                    with mock.patch("scripts.docker_runner.resolve_docker_binary", return_value="/usr/local/bin/docker"):
                        with mock.patch("scripts.docker_runner.run_subprocess", return_value=0) as run_subprocess:
                            exit_code = docker_runner.main(["run", "--value-file", str(value_file)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(run_subprocess.call_count, 2)
            self.assertEqual(run_subprocess.call_args_list[0].args[0][1:4], ["build", "--tag", docker_runner.IMAGE_NAME])

    def test_write_test_report_summarizes_unittest_output(self) -> None:
        output = "...\n----------------------------------------------------------------------\nRan 3 tests in 0.001s\n\nOK (skipped=1)\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("scripts.docker_runner.TEST_REPORT_DIR", Path(temp_dir)):
                report_path = docker_runner.write_test_report(
                    ["python", "-m", "unittest"],
                    output,
                    0,
                )

            report_text = report_path.read_text(encoding="utf-8")

        self.assertIn("| Status | PASS |", report_text)
        self.assertIn("| Passed | 2 |", report_text)
        self.assertIn("| Failed | 0 |", report_text)
        self.assertIn("| Skipped | 1 |", report_text)
        self.assertIn("## Raw Output", report_text)

    def test_docker_test_writes_report_and_opens_vscode(self) -> None:
        completed = CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout="Ran 1 test in 0.001s\n\nOK\n",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("scripts.docker_runner.TEST_REPORT_DIR", Path(temp_dir)):
                with mock.patch("scripts.docker_runner.ensure_image", return_value=0):
                    with mock.patch("scripts.docker_runner.docker_command", return_value=["docker", "run", "tests"]):
                        with mock.patch("scripts.docker_runner.run_subprocess_capture", return_value=completed):
                            with mock.patch("scripts.docker_runner.open_report_in_vscode") as open_report:
                                with mock.patch("sys.stdout", new_callable=io.StringIO):
                                    with mock.patch("sys.stderr", new_callable=io.StringIO):
                                        self.assertEqual(docker_runner.test(), 0)

            report_paths = list(Path(temp_dir).glob("unit-test-report-*.md"))

        self.assertEqual(len(report_paths), 1)
        open_report.assert_called_once_with(report_paths[0])


if __name__ == "__main__":
    unittest.main()
