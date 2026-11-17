## What and why

<!-- What changes, and the reason for it. Close the issue with "Fixes #NNN" or "Closes #NNN" if there is one. -->

## Testing notes

<!-- How a reviewer can verify the change. For UI changes, add Playwright screenshots or say why there are none. -->

## Checks

- [ ] Pre-commit hooks pass (prek runs the `poe check` hooks on every commit; run `poe check` yourself if you skipped them)
- [ ] `poe coverage` passes (backend changes)
- [ ] Tests added or updated for the change
- [ ] Docs updated where behaviour, configuration or the data model changed
- [ ] One focused change
- [ ] Breaking change (existing behaviour, API or data changes): the `breaking-change` label is applied
