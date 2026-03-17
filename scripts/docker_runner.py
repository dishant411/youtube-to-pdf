from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

IMAGE_NAME = "youtube-to-pdf:local"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "youtube-to-pdf"
DOCKER_CLI_CANDIDATES = [
    Path("/Applications/Docker.app/Contents/Resources/bin/docker"),
    Path("/usr/local/bin/docker"),
    Path("/opt/homebrew/bin/docker"),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the youtube-to-pdf Docker workflow safely.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor")
    subparsers.add_parser("build")
    subparsers.add_parser("test")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--value-file", required=True, help="File containing the raw URL value.")

    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("--value-file", required=True, help="File containing the batch file path.")
    return parser


def read_value_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def ensure_output_dir() -> Path:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_OUTPUT_DIR


def resolve_docker_binary() -> Optional[str]:
    docker_binary = shutil.which("docker")
    if docker_binary:
        return docker_binary

    for candidate in DOCKER_CLI_CANDIDATES:
        if candidate.exists() and candidate.is_file():
            current_path = os.environ.get("PATH", "")
            if str(candidate.parent) not in current_path.split(":"):
                os.environ["PATH"] = "{prefix}:{suffix}".format(prefix=candidate.parent, suffix=current_path)
            return str(candidate)
    return None


def docker_command(*args: str) -> List[str]:
    docker_binary = resolve_docker_binary()
    if docker_binary is None:
        raise RuntimeError("Docker is not installed or not on PATH.")
    return [docker_binary, *args]


def run_subprocess(command: Sequence[str]) -> int:
    completed = subprocess.run(list(command), check=False)
    return completed.returncode


def doctor() -> int:
    try:
        version_command = docker_command("version")
        info_command = docker_command("info")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if resolve_docker_binary() is None:
        print("Docker is not installed or not on PATH.", file=sys.stderr)
        return 1

    version_code = run_subprocess(version_command)
    if version_code != 0:
        print("Docker is installed but not reachable. Start Docker Desktop and try again.", file=sys.stderr)
        return version_code

    info_code = run_subprocess(info_command)
    if info_code != 0:
        print("Docker daemon is not responding.", file=sys.stderr)
        return info_code

    print("Docker is installed and reachable.")
    return 0


def build() -> int:
    return run_subprocess(docker_command("build", "--tag", IMAGE_NAME, str(REPO_ROOT)))


def test() -> int:
    return run_subprocess(
        docker_command(
            "run",
            "--rm",
            "--entrypoint",
            "python",
            IMAGE_NAME,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
        )
    )


def _runtime_prefix(output_dir: Path) -> List[str]:
    return docker_command(
        "run",
        "--rm",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=128",
        "--memory=512m",
        "--cpus=1.0",
        "--user",
        "65532:65532",
        "--mount",
        "type=bind,src={src},dst=/output".format(src=output_dir),
    )


def run_single(value_file: Path) -> int:
    url = read_value_file(value_file)
    output_dir = ensure_output_dir()
    command = _runtime_prefix(output_dir) + [
        IMAGE_NAME,
        "--url",
        url,
        "--output-dir",
        "/output",
    ]
    return run_subprocess(command)


def run_batch(value_file: Path) -> int:
    batch_file = Path(read_value_file(value_file)).expanduser().resolve()
    if not batch_file.exists() or not batch_file.is_file():
        print("Batch file does not exist: {path}".format(path=batch_file), file=sys.stderr)
        return 1
    try:
        batch_file.stat()
    except OSError:
        print("Batch file metadata could not be read: {path}".format(path=batch_file), file=sys.stderr)
        return 1

    output_dir = ensure_output_dir()
    command = _runtime_prefix(output_dir) + [
        "--mount",
        "type=bind,src={src},dst=/input,readonly".format(src=batch_file.parent),
        IMAGE_NAME,
        "--batch-file",
        "/input/{name}".format(name=batch_file.name),
        "--output-dir",
        "/output",
    ]
    return run_subprocess(command)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "build":
        return build()
    if args.command == "test":
        return test()
    if args.command == "run":
        return run_single(Path(args.value_file))
    if args.command == "batch":
        return run_batch(Path(args.value_file))
    return 1


if __name__ == "__main__":
    sys.exit(main())
