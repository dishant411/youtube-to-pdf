# YouTube to PDF

This project builds a Dockerized transcript-to-PDF workflow for YouTube videos. It accepts either a single video URL or a text file with one URL per line, fetches only YouTube-provided transcripts, formats the text into readable prose, and writes outputs into `~/Documents/youtube-to-pdf/`.

## Project Status

This project is early-stage and intended for local use. The Dockerized Python workflow is the supported path. The Node backend is experimental and may change.

## License

This project is available under the MIT License. See `LICENSE`.

## Prerequisites

- Docker Desktop or a compatible Docker Engine installed and running.
- `make` and `python3` available on the host.

Docker is required for all runtime work. The host does not need `pip`, `pandoc`, `yt-dlp`, or a Python virtual environment for this project to run.

## Setup From A Fresh Clone

```bash
git clone https://github.com/dishant411/youtube-to-pdf.git
cd youtube-to-pdf
cp .env.example .env
```

Edit `.env` and set:

```text
OPENAI_API_KEY=your_openai_api_key
```

Then verify the environment:

```bash
make doctor
make test
```

Run your first conversion:

```bash
make run URL='https://youtu.be/dQw4w9WgXcQ'
```

## Commands

```bash
make doctor
make build
make run URL='https://youtu.be/dQw4w9WgXcQ'
make batch FILE='examples/urls.txt'
make test
make clean
```

What each command does:

- `make doctor`: checks that Docker is installed, reachable, and that the Docker daemon is responding.
- `make build`: builds the local Docker image `youtube-to-pdf:local` from this repository.
- `make run URL='https://youtu.be/dQw4w9WgXcQ'`: runs one single YouTube URL through the converter and writes the PDF output into `~/Documents/youtube-to-pdf/`.
- `make batch FILE='examples/urls.txt'`: reads a text file with one URL per line and processes them as a batch job.
- `make test`: builds the image if needed, runs the test suite inside Docker, writes a Markdown report under `test-reports/`, and opens the report in VS Code when available.
- `make clean`: removes local temporary files created by the repo, such as `.make`, `.pytest_cache`, and Python `__pycache__` directories.

## One-command runner

If you want one script to use every time, use:

```bash
python3 run_converter.py 'https://youtu.be/dQw4w9WgXcQ'
python3 run_converter.py examples/urls.txt
```

What it does:

- validates that Docker is available
- on macOS, attempts to install Homebrew first if needed, then installs Docker Desktop
- if Docker is installed but the daemon is not running, it starts Docker Desktop automatically
- builds the Docker image automatically if it does not already exist
- treats an existing file path as a batch input
- treats an `http://` or `https://` argument as a single YouTube URL
- waits for the conversion to finish
- exits after the container has already been stopped and removed
- if this wrapper started Docker Desktop for the job, it quits Docker Desktop afterward

Optional rebuild:

```bash
python3 run_converter.py --rebuild 'https://youtu.be/dQw4w9WgXcQ'
```

If you use `zsh` and do not want quotes or escapes around watch URLs with `?v=`, add these functions to `~/.zshrc`:

```zsh
YOUTUBE_PDF_REPO="/absolute/path/to/youtubeToPdf"

function youtube-pdf() {
  python3 "$YOUTUBE_PDF_REPO/run_converter.py" "$@"
}
alias youtube-pdf='noglob youtube-pdf'

function youtube-pdf-rebuild() {
  python3 "$YOUTUBE_PDF_REPO/run_converter.py" --rebuild "$@"
}
alias youtube-pdf-rebuild='noglob youtube-pdf-rebuild'
```

Why this is needed:

- `zsh` expands `?` before `./run_converter.py` starts.
- a normal executable file cannot intercept that expansion
- the `noglob` alias is applied before the function receives arguments, so the raw URL is passed through unchanged

Then reload your shell:

```bash
source ~/.zshrc
```

After that, use:

```bash
youtube-pdf https://www.youtube.com/watch?v=hE4l9WyLF3U
youtube-pdf examples/urls.txt
youtube-pdf-rebuild https://www.youtube.com/watch?v=hE4l9WyLF3U
```

You do not need to manually close the runtime container after a conversion. The actual conversion runs with `docker run --rm`, so the container is removed automatically when the job finishes. This does not quit Docker Desktop itself; it only ensures the conversion container is gone.

## Automatic Docker install

When you run `run_converter.py` or the `youtube-pdf` shell function:

- if Docker is already installed, the converter proceeds normally
- if Docker is installed but not running, the script launches Docker Desktop and waits for the daemon
- if Docker is missing and Homebrew is missing, the script downloads and runs the official Homebrew installer
- after Homebrew is available, the script tries `brew install --cask docker`
- after installation, it launches Docker Desktop and waits for the Docker daemon to become ready
- if this wrapper launched Docker Desktop, it quits Docker Desktop after the conversion finishes
- if either Homebrew or Docker installation fails, the script stops and shows the failure

This bootstrap step is host-side setup, so it is not controlled by `requirements.txt`. The existing `requirements.txt` file is only for Python packages installed inside the Docker image.

## Accepted URL formats

- `https://www.youtube.com/watch?v=<video-id>`
- `https://youtu.be/<video-id>`
- `https://www.youtube.com/shorts/<video-id>`
- `https://www.youtube.com/embed/<video-id>`

The tool rejects non-YouTube URLs, playlist-only URLs, channel URLs, malformed video IDs, and URLs that embed other URLs in query parameters.

## Batch file format

Use a UTF-8 text file with:

- one URL per line
- blank lines ignored
- lines beginning with `#` ignored

An example file is provided at `examples/urls.txt`.

## Output

Outputs are written to:

```text
~/Documents/youtube-to-pdf/
```

Each successful video produces:

- `<sanitized-title>.pdf`
- if a file with the same title already exists, the tool writes `<sanitized-title>-2.pdf`, `<sanitized-title>-3.pdf`, and so on

## Behavior

- Single URL mode fails closed if no transcript is available.
- Batch mode skips missing transcripts and keeps going.
- English transcripts are summarized directly.
- Hindi auto-generated transcripts are fetched when English is unavailable, summarized first, and then the shorter summary is translated into polished English.
- The PDF title uses the clean YouTube title, not the video ID or link.
- The full YouTube URL is printed near the top of the PDF.
- The transcript body is optimized for readability.
- Timestamp markers are inserted into the PDF at 5-minute intervals such as `[00:05:00]`, `[00:10:00]`, and `[00:15:00]`.
- No sidecar JSON or manifest files are written.

## Security design

- Runtime processing happens inside Docker.
- The container runs as a non-root UID with a read-only root filesystem.
- The runtime container uses dropped capabilities, `no-new-privileges`, memory and CPU limits, and a `tmpfs` scratch space.
- Only the output directory is mounted for single runs.
- Batch runs mount the batch file parent directory read-only.
- User input is never passed through `shell=True`.
- Filenames are built from sanitized ASCII slugs.
- PDF text is rendered directly with ReportLab canvas primitives rather than interpreted HTML or markdown.
- `make` uses `$(value URL)` and `$(value FILE)` to avoid recursive evaluation of user input.

## Limitations

- Transcript-only in v1. There is no audio download or speech-to-text fallback.
- Playlist and channel ingestion are not supported.
- The Dockerized Python workflow is the supported runtime path; the Node backend is experimental.
- This repository pins exact package versions, but hash-locked installs were not generated here because the current environment has no network path for fetching package artifacts. If you want strict `--require-hashes`, generate the final lock file from a networked environment before production use.

## Contributing And Security

See `CONTRIBUTING.md` for development workflow and pull request expectations.

See `SECURITY.md` for vulnerability reporting and secret handling notes.
