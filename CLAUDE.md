@AGENTS.md

## Claude Code

- For any `.svelte` file or `.svelte.ts`/`.svelte.js` module, use the `svelte-file-editor` subagent.
- Before reporting a task complete, run only the relevant checks for the touched code (e.g. backend: `poe lint-backend`, `poe typecheck-backend`, `poe test-backend`; frontend: `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`). Do not run backend checks, mypy, or backend tests if nothing in the backend has changed. Alternatively, run `poe check-changed`.
- Never create, amend, stage, or push any git commit or any auto-commit workflow on the user's behalf. If a commit is needed, ask the user to commit instead and let them run the commit command themselves.

LLAP 🖖
