# Security policy

## Supported versions

Menagerist is pre-stable. Only the latest release (the `latest` image) and the current `edge` build receive security fixes.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Report it privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Include:

- the Menagerist version (`menagerist --version`, or the image tag),
- how you run it (Docker Compose, behind which reverse proxy),
- the steps to reproduce, and what an attacker could gain.

You can expect an acknowledgement within a few days. Fixes ship in a new release, and the advisory credits you unless you ask otherwise.

## Scope

In scope: authentication and sessions, authorisation between users, personal access tokens, uploads and media handling, backups, and anything that exposes one user's data to another.

Out of scope: problems that need an already-compromised host or admin account, and deployments that ignore the guidance in the README (for example, serving over plain HTTP on the public internet).
