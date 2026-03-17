#!/usr/bin/env python3
"""
Usage:
    ./run_converter.py 'https://youtu.be/dQw4w9WgXcQ'
    ./run_converter.py /path/to/urls.txt
    ./run_converter.py --rebuild 'https://youtu.be/dQw4w9WgXcQ'

Behavior:
    - Pass a YouTube URL to convert one video.
    - Pass a text file path to process one URL per line.
    - Output is written to ~/Downloads/youtube-to-pdf/.
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
from pathlib import Path
from urllib.request import urlopen
from typing import Optional, Sequence, Tuple

from scripts import docker_runner

HOMEBREW_INSTALL_URL = "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
BREW_CLI_CANDIDATES = [
    Path("/opt/homebrew/bin/brew"),
    Path("/usr/local/bin/brew"),
]
DOCKER_APP_NAME = "Docker"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the YouTube-to-PDF converter for either one URL or one batch file."
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
    completed = subprocess.run(
        [docker_binary, "image", "inspect", docker_runner.IMAGE_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def docker_daemon_ready() -> bool:
    docker_binary = docker_runner.resolve_docker_binary()
    if docker_binary is None:
        return False
    completed = subprocess.run(
        [docker_binary, "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
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
    print("Starting Docker Desktop...", file=sys.stderr)
    start_code = subprocess.run(
        ["open", "-a", DOCKER_APP_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode
    if start_code != 0:
        print("Failed to launch Docker Desktop.", file=sys.stderr)
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
    with tempfile.TemporaryDirectory() as temp_dir:
        value_file = Path(temp_dir) / "input.txt"
        value_file.write_text(value, encoding="utf-8")
        if mode == "batch":
            return docker_runner.run_batch(value_file)
        return docker_runner.run_single(value_file)


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
        if args.rebuild or not image_exists():
            build_code = docker_runner.build()
            if build_code != 0:
                return build_code

        exit_code = run_conversion(mode, value)
        if exit_code == 0:
            print("Finished. Output is in {path}".format(path=docker_runner.DEFAULT_OUTPUT_DIR))
            print("The conversion container has already exited and been removed.")
        return exit_code
    finally:
        if started_docker:
            stop_docker_desktop()


if __name__ == "__main__":
    sys.exit(main())
