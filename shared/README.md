# shared/

Files that **both the backend and the frontend read**. It has two folders:

| Folder                     | Holds                                                                                      | Used at                        |
| -------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------ |
| [`data/`](data/)           | Runtime data both sides need the same copy of                                              | Runtime (backend and frontend) |
| [`contracts/`](contracts/) | Test fixtures both test suites read, so two implementations of one rule cannot drift apart | Tests only                     |

Nothing else belongs here. Backend-only data (for example the example packs) lives with the module that owns it. Frontend-only assets live under `frontend/`. A file moves here only when the other side of the stack needs the same copy.

## data/

| File                 | What it is                                                                               | Read by                                                                                                                                                                                     |
| -------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `data/iso-data.json` | ISO 3166-1 countries and ISO 4217 currencies (plus the app-local currencies GPL and ZRU) | Backend: the built-in presets migration, through `app.platform.shared_data.shared_data_path("data/iso-data.json")`. Frontend: the money field's currency list, through the `$shared` alias. |

`iso-data.json` is generated, not hand-edited. Regenerate it with `poe generate-iso-data` (`scripts/generate_iso_data.py`, which pins `pycountry` so the runtime image does not carry it). See the "One shared data file for ISO countries and currencies" entry in [docs/DECISIONS.md](../docs/DECISIONS.md).

## contracts/

Test-only fixtures that **both test suites read**. They are not used at runtime.

| File                               | What it pins                                                                                                                                                                                                                                                                 | Read by                                                                                                                                                                                                                                    |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `contracts/regex-conformance.json` | `{pattern, value, expected}` cases for the regular expressions Menagerist generates or ships as built-ins (text starts-with and ends-with constraints, the phone and partial-date patterns). Python `re.search` and JavaScript's `u`-flag `RegExp` must agree on every case. | Backend: `test_text_constraints.py::test_conformance_cases_match_python_re`, through `shared_data_path("contracts/regex-conformance.json")`. Frontend: the "regex conformance fixture" block in `frontend/tests/text-constraints.test.ts`. |

**When to add a case:** whenever a pattern is generated or becomes a built-in kind, add accepting and rejecting cases for it, including non-ASCII digits and edge shapes. Both suites pick the new cases up automatically.

**What does not belong:** a case where the two engines are _meant_ to differ (for example Python's `$` also matching before a trailing newline). The fixture only holds behaviour that must be identical.

**Format:** keep non-ASCII text as `\uXXXX` escapes (write the file with `json.dump(..., ensure_ascii=True)`) so diffs stay small and reviewable.

See "Patterns" in [docs/field-types.md](../docs/field-types.md) for why generated patterns are held to both engines.

## How each side finds it

- **Backend:** `shared_data_path("<folder>/<name>")` returns the file. Locally it resolves to this directory. In the Docker image the installed package has no source tree, so the image sets `MENAGERIST_SHARED_DIR=/app/shared` and copies this directory there.
- **Frontend:** import through the `$shared` alias (`import iso from '$shared/data/iso-data.json'`), defined in `frontend/svelte.config.js` and `frontend/vite.config.ts`. Tests read `contracts/` by a path relative to the test file. In the Docker build the alias resolves to `/shared`.
- **Docker:** the `Dockerfile` copies `shared/` into both the frontend build and the runtime image, so a new file needs no Dockerfile change. (`contracts/` goes along for the ride: it is a few kilobytes and harmless in the image.)

## Adding a file

1. Check that both sides really need it. If only one does, keep it with that side.
2. Runtime data goes in `data/`; a fixture that exists to keep two implementations in step goes in `contracts/`.
3. Prefer a generated file with a script and a `poe` task (as for `iso-data.json`) over a hand-maintained one.
4. Read it from the backend through `shared_data_path` and from the frontend through `$shared` (or a path relative to the test, for contracts), never by a path that leaves the repo layout.
5. Add a row to the table for its folder, and for a contract add a test on each side that reads it.
