#!/usr/bin/env python3
"""
Usage:
    ./run_converter.py 'https://youtu.be/dQw4w9WgXcQ'
    ./run_converter.py /path/to/urls.txt
    ./run_converter.py --rebuild 'https://youtu.be/dQw4w9WgXcQ'

Behavior:
    - Pass a YouTube URL to convert one video.
    - Pass a text file path to process one URL per line.
    - Output is written to ~/Documents/youtube-to-pdf/.
    - The Docker runtime container is removed automatically after the job finishes.
    - In zsh, use a `youtube-pdf` function plus a `noglob` alias in ~/.zshrc to avoid quoting watch URLs.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence, Tuple
from urllib.request import urlopen

from app.env_loader import load_repo_env
from scripts import docker_runner

HOMEBREW_INSTALL_URL = "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
BREW_CLI_CANDIDATES = [
    Path("/opt/homebrew/bin/brew"),
    Path("/usr/local/bin/brew"),
]
DOCKER_APP_NAME = "Docker"
DOCKER_COMMAND_TIMEOUT_SECONDS = 30
SOURCE_STALE_PATHS = [
    Path("Dockerfile"),
    Path("requirements.txt"),
    Path("run_converter.py"),
    Path("app"),
    Path("scripts"),
    Path("node-backend") / "prompts",
]

load_repo_env()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the YouTube summary-to-PDF converter for either one URL or one batch file."
    )
    parser.add_argument("input_value", help="A single YouTube URL or a path to a batch file.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force a Docker image rebuild before running the conversion.",
    )
    return parser


def detect_mode(input_value: str) -> Tuple[str, str]:
    candidate = Path(input_value).expanduser()
    if candidate.exists():
        if not candidate.is_file():
            raise ValueError("Input path exists but is not a file: {path}".format(path=candidate))
        return "batch", str(candidate.resolve())

    if input_value.startswith(("https://", "http://")):
        return "single", input_value

    raise ValueError("Input must be a YouTube URL or an existing batch file path.")


def image_exists() -> bool:
    docker_binary = docker_runner.resolve_docker_binary()
    if docker_binary is None:
        return False
    try:
        completed = subprocess.run(
            [docker_binary, "image", "inspect", docker_runner.IMAGE_NAME],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=DOCKER_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


def _parse_docker_timestamp(value: str) -> Optional[datetime]:
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def image_created_at() -> Optional[datetime]:
    docker_binary = docker_runner.resolve_docker_binary()
    if docker_binary is None:
        return None
    try:
        completed = subprocess.run(
            [docker_binary, "image", "inspect", "--format", "{{.Created}}", docker_runner.IMAGE_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=DOCKER_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    return _parse_docker_timestamp(completed.stdout)


def latest_source_mtime() -> Optional[datetime]:
    repo_root = Path(__file__).resolve().parent
    latest = None
    for relative_path in SOURCE_STALE_PATHS:
        path = repo_root / relative_path
        if not path.exists():
            continue
        candidates = [path] if path.is_file() else [candidate for candidate in path.rglob("*") if candidate.is_file()]
        for candidate in candidates:
            mtime = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
            if latest is None or mtime > latest:
                latest = mtime
    return latest


def image_stale() -> bool:
    created_at = image_created_at()
    source_mtime = latest_source_mtime()
    if created_at is None or source_mtime is None:
        return False
    return source_mtime > created_at


def docker_daemon_ready() -> bool:
    docker_binary = docker_runner.resolve_docker_binary()
    if docker_binary is None:
        return False
    try:
        completed = subprocess.run(
            [docker_binary, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=DOCKER_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


def wait_for_docker(timeout_seconds: int = 120) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if docker_daemon_ready():
            return 0
        time.sleep(2)

    print(
        "Docker Desktop was installed but is not ready yet. Open Docker Desktop, wait for it to finish starting, and run the command again.",
        file=sys.stderr,
    )
    return 1


def docker_desktop_status() -> Optional[str]:
    docker_binary = docker_runner.resolve_docker_binary()
    if docker_binary is None:
        return None
    try:
        completed = subprocess.run(
            [docker_binary, "desktop", "status"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=DOCKER_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition(" ")
        if separator and key.strip().lower() == "status":
            return value.strip().lower() or None
    return None


def run_docker_desktop_command(action: str) -> int:
    docker_binary = docker_runner.resolve_docker_binary()
    if docker_binary is None:
        return 1
    try:
        return subprocess.run(
            [docker_binary, "desktop", action],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=180,
        ).returncode
    except subprocess.TimeoutExpired:
        print("Timed out while trying to {action} Docker Desktop.".format(action=action), file=sys.stderr)
        return 1


def resolve_brew_binary() -> Optional[str]:
    brew_binary = shutil.which("brew")
    if brew_binary is not None:
        return brew_binary
    for candidate in BREW_CLI_CANDIDATES:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return None


def install_homebrew() -> int:
    print("Homebrew is missing. Installing Homebrew from the official installer...", file=sys.stderr)
    with tempfile.TemporaryDirectory() as temp_dir:
        install_script = Path(temp_dir) / "install_homebrew.sh"
        try:
            with urlopen(HOMEBREW_INSTALL_URL, timeout=60) as response:
                install_script.write_bytes(response.read())
        except Exception as exc:
            print("Failed to download the Homebrew installer: {message}".format(message=exc), file=sys.stderr)
            return 1

        install_code = subprocess.run(
            ["/bin/bash", str(install_script)],
            env={**os.environ, "NONINTERACTIVE": "1"},
            check=False,
        ).returncode
        if install_code != 0:
            print("Homebrew installation failed.", file=sys.stderr)
            return install_code
    return 0


def start_docker_desktop() -> int:
    status = docker_desktop_status()
    if status == "running":
        print("Docker Desktop is running, but the Docker daemon is not healthy. Restarting Docker Desktop...", file=sys.stderr)
        restart_code = run_docker_desktop_command("restart")
        if restart_code != 0:
            print("Failed to restart Docker Desktop. Quit Docker Desktop completely, reopen it, and run the command again.", file=sys.stderr)
            return restart_code
        return wait_for_docker()

    print("Starting Docker Desktop...", file=sys.stderr)
    start_code = run_docker_desktop_command("start")
    if start_code != 0:
        try:
            start_code = subprocess.run(
                ["open", "-a", DOCKER_APP_NAME],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=DOCKER_COMMAND_TIMEOUT_SECONDS,
            ).returncode
        except subprocess.TimeoutExpired:
            start_code = 1
        if start_code != 0:
            print("Failed to launch Docker Desktop. Open Docker Desktop manually, wait until it says it is running, and run the command again.", file=sys.stderr)
            return start_code
    return wait_for_docker()


def stop_docker_desktop() -> int:
    if sys.platform != "darwin":
        return 0
    return subprocess.run(
        ["osascript", "-e", 'tell application "Docker" to quit'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode


def ensure_docker_available() -> tuple[int, bool]:
    if docker_daemon_ready():
        return 0, False

    if sys.platform != "darwin":
        print(
            "Docker is missing. Automatic install is only supported on macOS with Homebrew. Install Docker Desktop and run the command again.",
            file=sys.stderr,
        )
        return 1, False

    docker_binary = docker_runner.resolve_docker_binary()
    if docker_binary is not None:
        start_code = start_docker_desktop()
        if start_code != 0:
            return start_code, False
        return 0, True

    brew_binary = resolve_brew_binary()
    if brew_binary is None:
        brew_install_code = install_homebrew()
        if brew_install_code != 0:
            return brew_install_code, False
        brew_binary = resolve_brew_binary()
        if brew_binary is None:
            print("Homebrew was installed, but the brew binary could not be located.", file=sys.stderr)
            return 1, False

    print("Docker is missing. Installing Docker Desktop with Homebrew...", file=sys.stderr)
    install_code = subprocess.run([brew_binary, "install", "--cask", "docker"], check=False).returncode
    if install_code != 0:
        print("Docker Desktop installation failed.", file=sys.stderr)
        return install_code, False

    start_code = start_docker_desktop()
    if start_code != 0:
        return start_code, False
    return 0, True


def run_conversion(mode: str, value: str) -> int:
    print("Starting conversion in {mode} mode...".format(mode=mode), file=sys.stderr)
    with tempfile.TemporaryDirectory() as temp_dir:
        value_file = Path(temp_dir) / "input.txt"
        value_file.write_text(value, encoding="utf-8")
        if mode == "batch":
            return docker_runner.run_batch(value_file)
        return docker_runner.run_single(value_file)


def _list_pdf_outputs(output_dir: Path) -> set[Path]:
    if not output_dir.exists():
        return set()
    return {path.resolve() for path in output_dir.glob("*.pdf") if path.is_file()}


def _open_macos_outputs(output_dir: Path, pdf_paths: Sequence[Path]) -> None:
    if sys.platform != "darwin":
        return

    open_commands = [["open", str(output_dir)]]
    open_commands.extend([["open", "-a", "Preview", str(path)] for path in pdf_paths])

    for command in open_commands:
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0:
            print(
                "Could not open {target} automatically.".format(target=command[-1]),
                file=sys.stderr,
            )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        mode, value = detect_mode(args.input_value)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    ensure_code, started_docker = ensure_docker_available()
    if ensure_code != 0:
        return ensure_code

    doctor_code = docker_runner.doctor()
    if doctor_code != 0:
        return doctor_code

    try:
        if args.rebuild or not image_exists() or image_stale():
            if not args.rebuild and image_exists():
                print("Docker image is older than local source files. Rebuilding...", file=sys.stderr)
            build_code = docker_runner.build()
            if build_code != 0:
                return build_code

        output_dir = docker_runner.DEFAULT_OUTPUT_DIR
        before_pdfs = _list_pdf_outputs(output_dir)
        exit_code = run_conversion(mode, value)
        if exit_code == 0:
            after_pdfs = _list_pdf_outputs(output_dir)
            new_pdfs = sorted(after_pdfs - before_pdfs, key=lambda path: path.stat().st_mtime)
            _open_macos_outputs(output_dir, new_pdfs)
            print("Finished. Output is in {path}".format(path=docker_runner.DEFAULT_OUTPUT_DIR))
            print("The conversion container has already exited and been removed.")
        return exit_code
    finally:
        if started_docker:
            stop_docker_desktop()


if __name__ == "__main__":
    sys.exit(main())
