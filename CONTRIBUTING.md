# Contributing

Thanks for considering a contribution. This project is currently maintained as a small Docker-first YouTube transcript-to-PDF tool.

## Development Setup

1. Install Docker Desktop or a compatible Docker Engine.
2. Clone the repository.
3. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` if you want summary generation.
4. Run `make doctor`.
5. Run `make test`.

Do not commit `.env`, API keys, generated reports, or generated PDFs.

## Pull Requests

- Keep changes focused on one behavior or fix.
- Add or update tests for user-facing behavior.
- Run `make test` before opening a pull request.
- Update `README.md` when commands, setup, outputs, or limitations change.

## Code Style

- Prefer the existing Python standard library and project helpers before adding dependencies.
- Keep Docker runtime behavior hardened unless a change explicitly requires otherwise.
- Avoid `shell=True` for commands that include user input.
