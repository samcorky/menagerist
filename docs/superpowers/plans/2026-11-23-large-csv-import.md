# Large CSV imports: stored file, worker job, progress (#552)

Decisions (2026-11-23): the run is a worker job; limits rise to 50 MB and 50,000 rows while
keeping the single plan-then-apply pipeline (no chunked streaming).

## Shape

- **`ItemImport`** (transfer domain, owned, table `item_imports`): one uploaded file and what
  became of it. Status `uploaded → queued → running → succeeded | failed`. Holds the file's
  name and size, the options sent to run it (mapping, key field, connections, …), the
  requester's token grants (`None` for a session), the latest `ProgressSnapshot`, the result
  counts or the failure reason, `heartbeat_at` and `expires_at`.
- **`ImportFileStore`** port (put a byte stream with a size cap, open, delete), with a local
  adapter under `<media path>/imports/<owner>/<id>.csv` and an in-memory sibling.
- **Routes** under `/imports/items/files` (JSON bodies, no more multipart):
  - `POST` raw `text/csv` body → 201 `ItemImportResponse`
  - `GET` (own recent imports), `GET /{file_id}` (status, progress, result), `DELETE /{file_id}`
  - `POST /{file_id}/inspect`, `POST /{file_id}/plan` (run in the request, as now)
  - `POST /{file_id}/import` → 202, queues the run
- **Worker job `transfer.item_imports`** (heavy lane, coalesce, no schedule; an administrator's
  Run now just drains the queue). The API asks for a run through the shared `JobQueue` port from
  #737, which reuses a waiting run but queues one behind a running one, so no import is
  stranded. Runs of one job never overlap, so imports run one at a time across the instance.
  The handler drains queued imports in fair order (in turns between people, not strictly
  oldest first, so one person's five files cannot hold everyone back; a pure domain function,
  for the user to write), runs each as its owner (`ImportActors` port, bridged to identity: the owner's current roles
  plus the stored grants; a disabled or deleted account fails the import), writes progress to
  the import row, and marks a `running` import whose heartbeat is stale as failed (interrupted).
  So scheduling needs no per-run arguments (options an administrator picks per run are #738).
  The status response says how many imports are ahead ("Waiting: 1 import ahead of yours").
  Running several at once is a later setting (default 1) if waits matter.
- **Progress**: `ImportItems` takes an optional `ProgressReporter`; phases `read`, `check`
  (rows), `add` (items). A blocked plan ends as `fail` with its message.
- **Speed**: batch `check_item_attributes` across rows (`GraphTarget`), so a 50,000-row preview
  stays practical; measure 5,000 and 50,000 rows on Postgres.
- **Clean-up**: the file is deleted when its run finishes; rows and files expire after
  `MENAGERIST_TRANSFER_IMPORT_TTL_HOURS` (default 24) through a scheduled
  `transfer.prune_imports` job.

## Layers (gh stack)

0. **#737**: queueing a job for work someone started (`JobQueue`, `QueueJobRun`), and
   `poe serve` starts the worker. The e2e harness already runs a worker per instance.
1. **Backend**: domain, store, routes, job, bridges, migration, settings docs, regenerated
   client. Old multipart routes stay so the frontend and e2e keep passing.
2. **Frontend and e2e**: upload once, then inspect/plan/import by id; poll the import and show a
   progress bar; the import page shows a running import on return. Remove the multipart routes.

## Verification

`poe test-backend-fast` while iterating; router, adapter and integration tests for touched code;
`poe typecheck-backend`, `poe lint-backend`, `poe coverage`, `poe lint-schema`; frontend
typecheck, unit tests and the CSV import e2e spec.
