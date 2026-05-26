# Security Policy

## Supported Versions

This project is early-stage. Security fixes are handled on the default branch.

## Reporting a Vulnerability

Please do not open public issues for secrets, credential leaks, command injection, path traversal, or container escape concerns.

Report security concerns by contacting the repository owner directly through GitHub.

## Secret Handling

- Never commit `.env` files.
- Use `.env.example` for placeholders only.
- Rotate any API key that may have been committed, pasted into an issue, or exposed in logs.
- Before making the repository public, scan git history for real credentials.
