# Scheduler: background jobs for backups, update checks, purging and expiry: plan

Status (2026-10-28): Phases 0-3 are implemented (queue, worker, `job` CLI, readiness check, scheduled backups); Phases 4-6 are not. Permissions are `scheduling:job:read` and `scheduling:job:run`. Rewritten 2026-10-23 after reading the repo (branch `feature/initial-implementation`, commit a6cb581), replacing the 2026-10-22 version. It folds in the answers Sam gave on 2026-10-22 (decisions list) and corrects several things the earlier version got wrong (see "What the repo changed").

This document includes the code sketches (Appendix A) and the event and outbox candidate catalogue (Appendix B) that used to be separate files. Related: `2026-10-25-settings-and-config.md` (where schedules and other tunables come from; the scheduler only sees `ScheduleSource`).

Working rules (`AGENTS.md`, `CLAUDE.md`): never create, stage or push commits (ask Sam to commit); British English; `.svelte` files go through `svelte-file-editor`; run only relevant `poe` checks (`lint-backend`, `typecheck-backend`, `test-backend`, `coverage` before calling backend work done); coverage floors domain/application/shared_kernel 100%, adapters 80%, platform 70%; every port has an in-memory sibling; dependencies only when strictly necessary, checked against `.github/renovate.json` and image size; no abstractions beyond the task; do not create docs unless asked.

## Goal

Run recurring and ad hoc jobs outside the HTTP path, safely and visibly: scheduled backups first, then update checks, purging of expired or deleted data, expired sessions and API tokens, and media cleanup. The engine sits behind ports so it can be swapped. Existing use cases stay the units of work; the scheduler is a driving adapter that calls them as `SYSTEM_ACTOR`.

## Decisions already made (Sam, 2026-10-22/23)

1. Separate worker process, a Cyclopts command in the same image, a required service in the default compose file; a warn-only readiness check says if no worker has run recently.
2. Schedules from deployment config now, admin UI later (DB-backed instance settings).
3. Timezone: instance level, from `TZ` (Docker standard), else `MENAGERIST_TIMEZONE`. My reading of the fallback: `TZ`, then `MENAGERIST_TIMEZONE`, then UTC. Confirm.
4. Backups: default daily at a quiet hour (03:00 instance time), existing retention pruning, can be turned off.
5. Update check: on by default, daily, GitHub Releases, no instance identifier, quiet on failure, admin-only banner, env switch off.
6. Own bounded context: `modules/scheduling`.
7. Two lanes: `default` and `heavy`; backups on `heavy`.
8. Run history: last N runs per job (default 100, a setting).
9. Worker refuses and skips jobs while a restore is running.
10. Swappable engine behind ports (like APScheduler's stores); lanes and coalescing wanted.
11. No event system exists, so the scheduler must not depend on one (and does not need to; see the events section).
12. `ClaimOrphaned*` flows are one-off and setup-gated, not scheduler jobs.

## What the repo changed

- **`ClaimOrphaned*` is already setup-gated** (`entrypoints/api/shared/bridges/claim_existing_data.py`, `backup_setup_gate.py`). Nothing to do for the scheduler; decision 12 needs no work beyond "keep it out of the registry".
- **A `System` access stance and `SYSTEM_ACTOR` already exist** (`shared_kernel/access.py`, `actor.py`), and `media cleanup` already runs as the system actor. The access plan's Q4 is effectively answered for jobs.
- **croniter is not a backend dependency** (earlier I said it was). A cron parser is a new dependency either way. `cronsim` 2.7 has no dependencies, and I tested it in Europe/London: a daily 03:00 stays at 03:00 across both changes, a local time that does not exist (01:30 on the spring change) runs once at the first valid time (02:00 BST), a repeated local time (01:30 in autumn) runs once, hourly runs both 01:00s, and invalid expressions raise `CronSimError`. It silently accepts naive datetimes, so our wrapper must require timezone-aware input.
- **`SchedulerRuntime` should not be a port.** `backend/README.md` says scheduler consumers are driving adapters, the scheduler port takes a `job_key` string, and the registry stays inbound. The worker loop is a driving adapter; only the queue, run store and schedule source are driven ports. A `Clock` port is also unnecessary: pass `now` into pure functions.
- **Restore already has a lock to honour.** `platform/advisory_locks.py` defines `SETUP_LOCK_KEY` and `BACKUP_RESTORE_LOCK_KEY`, and `database_restorer.py` takes a table lock. My earlier "marker outside the database" is not needed; the worker checks the existing advisory lock. Phase 0 confirms the lock mode and that a try-lock is safe.
- **Cleanup use cases already exist and run from the CLI** (`backup` and `media` apps, `PruneBackups`, `CleanupExpiredMedia`), so today they rely on external cron. Scheduling them is wiring, not new business logic. Two caveats: `PruneBackups` also removes orphans and expired user exports, and `CleanupExpiredMedia` loads its candidates without a limit.
- **Expired sessions are swept opportunistically on sign-in** (`modules/identity/application/sign_in.py`, `delete_expired`). That is a purge job hiding in a request path.
- **Pending purge work is already planned elsewhere**: `data purge-deleted` and `purge-removed-examples` (smart-collections plan, Part D) and expired API tokens (`2026-10-23-api-tokens.md`). These are the purging and token-expiry jobs.
- **The Docker setup**: one hardened `menagerist` service (read-only root, `tmpfs`, uid 1000, `serve --migrate`) with `media-data` and `./backups` volumes. The worker is a second service reusing the same anchors and volumes.
- **Dual-write gap in my old sketch.** Enqueueing a job after committing the data change can lose the job on a crash. See "Transactional enqueue" below.

## Engine decision

Two realistic options. The ports are the same for both, so this is reversible.

| | In-house Postgres queue (asyncpg/SQLAlchemy, our `job_runs` table) | Procrastinate 3.10 |
|---|---|---|
| New runtime dependencies | `cronsim` only | `procrastinate` plus psycopg 3 and its pool, asgiref, attrs, croniter, python-dateutil (7 runtime dependencies in total, per its pyproject) |
| Drivers | one (the app's existing one) | second Postgres driver and pool beside asyncpg |
| Enqueue in the caller's transaction | yes, trivially (same session) | not with asyncpg; would need an external-connection pattern |
| Cron in a non-UTC zone | ours, tested (cronsim) | evaluated by the engine; spike needed |
| Queues, retries, stalled-job recovery, locks | we write them (small: claim with `FOR UPDATE SKIP LOCKED`, heartbeat, reaper) | built in |
| Maintenance risk | ours | maintainers are asking for help; Python 3.14 status unconfirmed |
| Late-run window | ours (policy per job) | 10 minutes by default |

**Recommendation: in-house adapter, tick-driven ("Option B").** The engine only has to provide a durable queue and a one-minute tick; the domain computes what is due. That removes most of what Procrastinate would give us, keeps one driver and one new tiny dependency, makes transactional enqueue free, and fits `AGENTS.md` on dependencies and image size. Procrastinate stays a possible second adapter behind the same ports and contract suite. This reverses my earlier lean; the cause is Option B plus the repo findings, not a flaw found in Procrastinate. Sam decides.

Tick-driven means: worst-case latency is about a minute (irrelevant for these jobs), and the worker must always run. Anything needing near-real-time delivery (an outbox relay, see below) is a worker loop, not a cron job.

## Design

### Units of work
Jobs are `UseCase`s with an access stance (`System` for pure system jobs). The worker resolves a `job_key` to a handler and calls `handle(request, SYSTEM_ACTOR)`. No business logic in the scheduler.

### Job definition (inbound registry, domain data)
Placement: the value types (`JobDefinition`, `Lane`, `Overlap`, `MissedRun`) live in `shared_kernel/jobs.py`, like `Actor`, because modules do not import each other. Each owning module contributes its jobs from its own adapters (for example `modules/backup/adapters/scheduling/jobs.py`); the composition root collects them into the registry. `modules/scheduling` owns the registry, ports, queue, worker and API, and imports no other module.
`JobDefinition`: `job_key` (for example `backup.create`), handler factory, default schedule or none, `lane`, `overlap` (`skip`, `coalesce`, `queue`), `missed_run` (`skip`, `run_once`) and `max_lateness`, retry policy (only for idempotent jobs), `run_now_allowed`, and `needs_setup_complete` (jobs skip until the instance is set up). One registry module lists every job. Architecture tests: keys are unique, each handler's use case declares a stance, and nothing outside the adapter imports the engine or `cronsim`.

### Pure scheduling logic (domain)
`due_runs(definitions, schedules, last_scheduled, tz, now) -> list[DueRun]`. Fire times in `(watermark, now]` are computed with `cronsim` in the instance zone, converted to UTC. The watermark is the latest `scheduled_for` already recorded for that job; a job seen for the first time starts at `now` (no backfill). With several missed fire times: `skip` drops them all; `run_once` keeps only the latest, and only if within `max_lateness`. The run id is `uuid5(JOB_NAMESPACE, f"{job_key}:{fire_time_utc.isoformat()}")`, so two workers ticking at once create the same run and the unique key makes the second insert a no-op. No clock port; tests pass `now`.

### Ports (application layer; each has an in-memory sibling)
- `JobRunQueue` (driven): `enqueue(run)` idempotent on run id; `claim(lanes, worker_id)` returns the next queued run; `heartbeat(run_id)`; `finish(run_id, outcome)`; `reap_abandoned(older_than)`. Keyed by `job_key` string.
- `JobRunReader` (query side): last run, history, next planned run per job, worker liveness.
- `ScheduleSource` (driven): `schedule_for(job_key) -> str | None`, the one question the scheduler asks. Where the answer comes from (deployment env, admin UI, per-user overrides) is `2026-10-25-settings-and-config.md`'s business, not the scheduler's; its Phase F wires `ScheduleSource` to `SettingsReader`. Until that plan exists the adapter reads the module's env settings (for example `BackupSettings.schedule`), and the adapter is the only thing that changes when layered settings arrive.
- `JobRunRecorder`: started, succeeded, failed, skipped, abandoned. In the in-house adapter it writes the same row the queue uses; with another engine it writes our `job_runs` table so history never depends on engine tables.
- **Not ports:** the worker loop (driving adapter under `adapters/cli`), the registry (inbound), any clock.

### Transactional enqueue
`JobRunQueue.enqueue` takes the caller's unit of work, so a use case can write its data and enqueue a job in one transaction. Run-now and the tick use the same call. This closes the dual-write gap in the old sketch, and it is also exactly the outbox pattern for single-handler work (see events section).

### Policies
- **Lanes**: `default`, `heavy`. One worker consumes both. A claim never waits on the other lane.
- **Overlap** (job already queued or running): `skip` drops the new run; `coalesce` keeps one waiting run; `queue` stacks. Backups: `coalesce`. Update check: `skip`.
- **Run now**: idempotent; if a run for that job is queued or running, return its id.
- **Restore guard**: before executing a claimed run, the wrapper try-locks `BACKUP_RESTORE_LOCK_KEY` in the mode that conflicts with restore; if it cannot, the run is recorded `skipped` with reason `restore_in_progress`. Also skip when setup is not complete for jobs with `needs_setup_complete`.
- **Crash handling**: running rows without a heartbeat for N minutes become `abandoned` (reaper runs on every tick). Abandoned runs are not retried unless the job declares itself idempotent with retries.
- **Batching**: purge jobs take a `limit` and loop in bounded batches with a time budget, each batch its own unit of work, so a large backlog never holds one long transaction.

### Settings
`SchedulerSettings(MenageristBaseSettings)`, tested in the sandbox (14 cases):

```python
class SchedulerSettings(MenageristBaseSettings):
    model_config = SettingsConfigDict(
        frozen=True, validate_default=True, env_prefix="MENAGERIST_",
        extra="ignore", env_ignore_empty=True,   # group-local, not on the base
    )
    timezone: ZoneInfo = Field(
        default_factory=lambda: ZoneInfo("UTC"),
        validation_alias=AliasChoices("TZ", "MENAGERIST_TIMEZONE"),
    )
    run_history_per_job: int = Field(
        default=100, ge=1, validation_alias="MENAGERIST_SCHEDULER_RUN_HISTORY_PER_JOB"
    )
```

Notes: `env_ignore_empty` must stay group-local because `MENAGERIST_BACKUP_SCHEDULE=` must still mean "off". With `AliasChoices` the prefix is not applied, so each alias is spelled in full. A native `ZoneInfo` field reports unknown zones as normal validation errors. If the string is wanted (logging, JSON, API), use `Annotated[str, AfterValidator(check_zone)]`; `ValidateAs(str, check_zone)` also works, but `ValidateAs(ZoneInfo, ...)` leaks raw `ZoneInfoNotFoundError` and breaks `model_dump(mode="json")`, which the startup settings log uses. Ship `tzdata` if the runtime image has no zoneinfo (Phase 0 checks). Module settings add `*_schedule` cron strings validated with `cronsim` at startup, empty meaning off. All groups join `INSTANCE_SETTINGS` for the startup log.

### CLI and compose
- `menagerist worker`: the loop (tick every 60 s, claim, execute, heartbeat, reap). Graceful shutdown on SIGTERM: stop claiming, let the current run finish up to a grace period.
- `menagerist job list` / `menagerist job run <job_key>`: the "Cron adapter". It runs one job synchronously through the same wrapper, so people who prefer system cron or a Kubernetes CronJob can skip the worker, and it is a debugging tool.
- Compose: a `worker` service using the `*hardened` and `*logging` anchors, `command: ["worker"]`, the same `media-data` and `./backups` mounts, the same `MENAGERIST_DATABASE_URL`, `TZ` shared through an anchor or `.env`, no ports, `depends_on` postgres healthy. The worker never migrates; it waits and retries until the schema matches the expected head (the API runs `--migrate`).
- Readiness: warn-only `scheduler:worker` check (no heartbeat in N minutes), same rule as the proxy and CORS checks; never takes the instance out of rotation.

## Job catalogue

| `job_key` | Does | Default | Lane / policy | Notes |
|---|---|---|---|---|
| `backup.create` | `create_backup(label=...)` | daily 03:00 | heavy, coalesce, run_once | Existing `before_migrate` backup stays; scheduled backups get a different label |
| `backup.prune` | `PruneBackups`: retention, orphans, expired user exports | hourly | default, coalesce | Separate from create so user exports expire on time even with backups off |
| `system.update_check` | `ReleaseFeed.latest_release()`, store result | daily | default, skip | New port plus GitHub adapter; env switch off |
| `media.cleanup` | `CleanupExpiredMedia` (staged and orphaned TTLs) | hourly | default, coalesce | Add a batch limit first |
| `identity.sessions.purge_expired` | delete expired sessions | daily | default, coalesce | Replaces the sign-in sweep once shipped (Sam to decide) |
| `identity.api_tokens.purge_expired` | delete tokens expired or revoked beyond retention | daily | default, coalesce | Expiry is enforced at authentication; this is tidiness only. Keep revoked rows for audit for a stated period |
| `data.purge_deleted` | soft-deleted data past retention (smart-collections Part D) | off | heavy, skip | Destructive; run-now only until a retention setting exists |
| `data.purge_removed_examples` | removed example data | off | default, skip | Same |
| `scheduling.prune_runs` | keep last N runs per job | daily | default, coalesce | Our table only |

Not scheduler jobs: `ClaimOrphaned*` (setup flow), the pre-migration backup (start-up), restore (interactive, guarded by the advisory lock).

## Events and the outbox: when and why

First, a distinction that removes most of the pressure to build an event system: a transactional job queue **is** the outbox pattern for work with one known handler. Writing the data and the queued run in one transaction gives at-least-once delivery without events. Events and an outbox table are only needed when work must fan out to several or unknown subscribers, or when the reaction must be recorded as a fact (audit, webhooks).

| Stage | What exists | Build it when (trigger) | Why not earlier |
|---|---|---|---|
| 0, now | Scheduler, transactional enqueue, `job_runs` | Phase 1-3 | Time-driven jobs need no events |
| 1 | Single-handler reactions are jobs enqueued in the use case's unit of work | First change-driven task with one handler: thumbnail regeneration after upload, delete the file when a media row is deleted, enrichment lookup after save | No event system required; same table, same worker |
| 2 | In-process domain events (aggregates raise, the unit of work collects and dispatches after commit; the `on_commit` hook on the unit of work is the seam) | Two or more modules must react to the same fact without importing each other: user deletion cleaning settings, media and shares; audit or activity history; notifications | A missed event is acceptable only if it is rebuildable or harmless, otherwise go to stage 3 |
| 3 | Outbox table written in the same transaction, relay worker, at-least-once with idempotent handlers | First consumer outside our database or process that must not miss a change: search or ML sidecars, outbound webhooks and plugins, external APIs | Needs event ids, consumer dedupe, ordering and retention decisions; design them for the real consumer |
| 4 | `LISTEN/NOTIFY` wake-up for the relay, replay and admin view of failed events | Poll latency or backlog becomes a real complaint | Polling every few seconds is enough first |

Rules that keep the later stages cheap: use cases enqueue through `JobRunQueue` with the caller's unit of work (never after commit); every handler is idempotent on its run or event id; run and event ids are deterministic or unique-keyed; the relay (stage 3) is a worker loop, not a per-minute cron job; audit records are a product requirement, so decide at stage 2 whether the outbox row doubles as the audit row. Do not build stage 2 or 3 for the scheduler's own sake; run recording stays a direct call to `JobRunRecorder` in the wrapper.

## Phases (each shippable alone)

**Phase 0: verify (no repo changes).** Confirm: the restore lock mode and a safe try-lock; how `CreateBackup` and `PruneBackups` are invoked and whether `create_backup(label=...)` can be called from a use-case handler; that the image has zoneinfo (else add `tzdata`); `CleanupExpiredMedia` batching; the Alembic revision style for a `job_runs` table; the readiness check wiring (`ReadinessCheckRegistry`); the current dependency list against Renovate rules. Checkpoint: Sam confirms engine (in-house) and Option B.

**Phase 1: domain, ports, in-memory adapters.** `modules/scheduling`: `JobDefinition`, registry, `due_runs`, the five ports with in-memory siblings, the run-now use case, status queries, `SchedulerSettings`, and the shared contract suite (lanes, `skip`, `coalesce`, `run_once` with `max_lateness`, idempotent ids, abandoned reaping, DST cases with fixed `now`). Unit tests at 100%.

**Phase 2: Postgres adapter, worker, compose, readiness.** `job_runs` migration; claim with `FOR UPDATE SKIP LOCKED`; heartbeat and reaper; the execution wrapper (restore guard, setup gate, recorder); `menagerist worker` and `menagerist job list/run`; compose `worker` service; `scheduler:worker` check; `scheduling.prune_runs`. The contract suite runs against Postgres under `@pytest.mark.integration`.

**Phase 3: scheduled backups.** `backup.create` and `backup.prune` jobs and `MENAGERIST_BACKUP_SCHEDULE`; end-to-end test with the in-memory adapters; volume documentation.

**Phase 4: update check.** `ReleaseFeed` port, GitHub adapter, in-memory sibling, calver comparison in the domain, stored result, enable switch, admin query and banner (via `svelte-file-editor`).

**Phase 5: housekeeping jobs.** `media.cleanup` (with batching), session and API-token purge, and the optional purge jobs (off by default). Decide on removing the sign-in sweep.

**Phase 6: run now, history and status UI.** Routes under the system router (`/api/v1/system/jobs`, `.../runs`, `POST .../run` returning 202 with the run id), permissions (`scheduling:job:read`, `scheduling:job:run`, admin-only, not token-grantable except via the Admin preset), generated client, admin page (via `svelte-file-editor`).

**Later.** Admin-editable schedules, via `2026-10-25-settings-and-config.md` Phase F (only the `ScheduleSource` adapter changes); a second engine adapter if ever wanted; event stages 1-4 as triggered.

## Risks

- Writing a queue ourselves: small, but the claim, heartbeat and reaper must be tested for crashes and two workers. The contract suite and a two-worker integration test are the mitigation.
- Worker down means no backups: the readiness warning, compose default and docs are the mitigation; `menagerist job run` and external cron remain a fallback.
- Worker without the API's volumes would back up nothing: mount parity is documented and `backup.create` fails loudly if the data directory is missing.
- Daylight saving and a missing zoneinfo: `cronsim` behaviour is tested above; fail-fast settings validation; `tzdata` if needed.
- Restore clobbering history: a restore replaces `job_runs`; the reaper and the watermark rule treat a changed table as a fresh start with no backfill.
- Unbounded purges: batch limits and time budgets from the start.
- Destructive purge jobs: off by default and run-now only until retention settings exist.

## Still open for Sam

0. Layered settings now have their own plan (`2026-10-25-settings-and-config.md`). The scheduler only needs `ScheduleSource` from it; schedules tunable in the UI arrive with that plan's Phase F.

1. Engine: in-house asyncpg adapter (recommended) or Procrastinate; and confirm Option B (tick-driven).
2. Timezone fallback order (`TZ`, `MENAGERIST_TIMEZONE`, UTC) and the default history of 100 runs per job.
3. Remove the opportunistic session sweep from sign-in once `identity.sessions.purge_expired` ships?
4. Should `data.purge_*` ever run on a schedule, or stay manual?
5. Should `backup.prune` run hourly (so user exports expire on time) or only after each backup?

## Appendix A: code sketches

Sketches only except section 3 (cron logic), which is tested: 10 pytest cases in the sandbox with `cronsim` 2.7, Europe/London daylight-saving cases included. Not compiled or type-checked otherwise; class names are suggestions that follow the repo layout I read.

### 0. The flow in one picture

```
env: TZ, MENAGERIST_BACKUP_SCHEDULE, ...
  -> settings groups (SchedulerSettings, BackupSettings)
  -> SettingsReader / ScheduleSource  (2026-10-25-settings-and-config.md Phase F; env pin > admin value > code default)
  -> worker (driving adapter, tick every 60 s)
       -> for each scheduled job: schedule_for(job_key) -> due_fire(...) -> queue.enqueue(run)   [idempotent on run id]
       -> claim(lanes) -> execute wrapper -> use case as SYSTEM_ACTOR -> recorder
web UI / CLI:  POST /jobs/{key}/run  or  menagerist job run <key>  -> RunJobNow -> queue.enqueue(run) in the caller's unit of work
```

### 1. Job definition and registry (inbound; domain data)

```python
# shared_kernel/jobs.py   (value types live here so no module imports modules/scheduling)
@dataclass(frozen=True, slots=True)
class JobDefinition:
    job_key: str                                   # "backup.create"
    run: Callable[[Actor], Awaitable[None]]        # bound to a use case by the composition root
    lane: Lane = Lane.DEFAULT                      # DEFAULT | HEAVY
    overlap: Overlap = Overlap.COALESCE            # SKIP | COALESCE | QUEUE
    missed_run: MissedRun = MissedRun.SKIP         # SKIP | RUN_ONCE
    max_lateness: timedelta = timedelta(minutes=10)
    schedule_key: str | None = None                # key passed to ScheduleSource; None = run-now only
    run_now: bool = True
    needs_setup_complete: bool = True
    retries: int = 0                               # only for idempotent jobs
```

```python
# modules/backup/adapters/scheduling/jobs.py   (each module contributes its own)
def backup_jobs(uc: BackupUseCases) -> tuple[JobDefinition, ...]:
    async def create(actor: Actor) -> None:
        await uc.create_scheduled_backup().handle(CreateBackupCommand(label="scheduled"), actor)

    async def prune(actor: Actor) -> None:
        await uc.prune_backups().handle(PruneBackupsCommand(), actor)

    return (
        JobDefinition("backup.create", create, lane=Lane.HEAVY, overlap=Overlap.COALESCE,
                      missed_run=MissedRun.RUN_ONCE, max_lateness=timedelta(hours=12),
                      schedule_key="backup.schedule"),
        JobDefinition("backup.prune", prune, schedule_key="backup.prune_schedule"),
    )
```

The registry is a dict with duplicate and unknown-key errors (`DuplicateJob`, `UnknownJob`, both domain errors); the composition root concatenates every module's tuple.

### 2. Ports (application layer, each with an in-memory sibling)

```python
# modules/scheduling/ports/
class JobRunQueue(Protocol):
    async def enqueue(self, run: NewRun, uow: UnitOfWork) -> RunState: ...
        # transactional: joins the caller's session; idempotent on run.id; applies overlap policy
    async def claim(self, lanes: Sequence[Lane], worker_id: str, now: datetime) -> ClaimedRun | None: ...
    async def heartbeat(self, run_id: UUID, now: datetime) -> None: ...
    async def finish(self, run_id: UUID, outcome: Outcome, now: datetime, error: str | None = None) -> None: ...
    async def reap_abandoned(self, older_than: datetime) -> int: ...

class JobRunReader(Protocol):                      # query side, no UoW
    async def last_scheduled_for(self, job_key: str) -> datetime | None: ...
    async def active_run(self, job_key: str) -> RunState | None: ...
    async def history(self, job_key: str, *, limit: int) -> Sequence[RunState]: ...
    async def worker_alive(self, since: datetime) -> bool: ...

class ScheduleSource(Protocol):
    async def schedule_for(self, schedule_key: str) -> str | None: ...   # cron expression, or None for off

class JobRunRecorder(Protocol):                    # started / succeeded / failed / skipped / abandoned
    ...
```

Not ports: the worker loop (driving adapter under `modules/scheduling/adapters/cli`), the registry, any clock (functions take `now`).

### 3. Cron logic (tested)

```python
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from cronsim import CronSim, CronSimError

TICK = timedelta(minutes=1)
_MAX_FIRES = 1_000


class MissedRun(StrEnum):
    SKIP = "skip"
    RUN_ONCE = "run_once"


class InvalidCron(ValueError): ...


@dataclass(frozen=True, slots=True)
class CronSchedule:
    expression: str
    zone: ZoneInfo

    def __post_init__(self) -> None:
        try:
            CronSim(self.expression, datetime.now(self.zone))
        except CronSimError as exc:
            raise InvalidCron(self.expression) from exc

    def fires_between(self, after: datetime, until: datetime) -> list[datetime]:
        """Fire times in (after, until], as UTC. Both arguments must be aware."""
        if after.tzinfo is None or until.tzinfo is None:
            raise ValueError("timezone-aware datetimes required")
        sim = CronSim(self.expression, after.astimezone(self.zone))
        fires: list[datetime] = []
        for local in sim:
            moment = local.astimezone(UTC)
            if moment > until:
                break
            fires.append(moment)
            if len(fires) >= _MAX_FIRES:
                break
        return fires


def due_fire(
    schedule: CronSchedule,
    *,
    watermark: datetime | None,
    now: datetime,
    missed: MissedRun,
    max_lateness: timedelta,
) -> datetime | None:
    """The one fire time to enqueue now, or None. A new job starts from `now`."""
    fires = schedule.fires_between(watermark or now - TICK, now)
    if not fires:
        return None
    latest = fires[-1]
    grace = max_lateness if missed is MissedRun.RUN_ONCE else TICK
    return latest if now - latest <= grace else None


def run_id_for(job_key: str, fire: datetime) -> UUID:
    return uuid5(NAMESPACE_URL, f"menagerist:{job_key}:{fire.astimezone(UTC).isoformat()}")
```

Behaviours covered by the tests: fires on time; not due between fires; `RUN_ONCE` catches up within `max_lateness`; `SKIP` ignores a late run; several missed fires collapse to the latest; a local time repeated in autumn runs once; a local time that does not exist in spring runs once at the first valid time (02:00 BST); the same fire time always gives the same run id; invalid expressions and naive datetimes are rejected.

### 4. The tick and the execution wrapper

```python
# modules/scheduling/application/tick.py  (not a UseCase: the worker owns it, runs as the system actor)
async def tick(registry, schedules, reader, queue, zone, now, uow_factory) -> None:
    for job in registry.scheduled():
        expression = await schedules.schedule_for(job.schedule_key)
        if expression is None:
            continue
        fire = due_fire(CronSchedule(expression, zone),
                        watermark=await reader.last_scheduled_for(job.job_key),
                        now=now, missed=job.missed_run, max_lateness=job.max_lateness)
        if fire is not None:
            async with uow_factory() as uow:
                await queue.enqueue(NewRun(id=run_id_for(job.job_key, fire), job_key=job.job_key,
                                           lane=job.lane, scheduled_for=fire, requested_by=None), uow)
                await uow.commit()
```

```python
# modules/scheduling/application/execute.py
async def execute(claimed, job, *, recorder, restore_lock, setup_state, now) -> None:
    if job.needs_setup_complete and not await setup_state.is_complete():
        return await recorder.skipped(claimed.id, now(), "setup_incomplete")
    async with restore_lock.try_hold() as held:      # try-lock on BACKUP_RESTORE_LOCK_KEY; Phase 0 confirms the mode
        if not held:
            return await recorder.skipped(claimed.id, now(), "restore_in_progress")
        try:
            await job.run(SYSTEM_ACTOR)
        except Exception as exc:                      # worker boundary: a try/except is fine here
            await recorder.failed(claimed.id, now(), repr(exc))
            return
        await recorder.succeeded(claimed.id, now())
```

### 5. In-house Postgres adapter (the claim, in SQL)

```sql
-- job_run(id uuid pk, job_key text, lane text, state text, scheduled_for timestamptz,
--         requested_by uuid null, worker_id text null, heartbeat_at timestamptz null, ...)
-- enqueue (idempotent; coalesce also needs a partial unique index on (job_key) WHERE state = 'queued')
INSERT INTO job_run (id, job_key, lane, state, scheduled_for, requested_by)
VALUES (:id, :job_key, :lane, 'queued', :scheduled_for, :requested_by)
ON CONFLICT DO NOTHING;

-- claim
UPDATE job_run SET state = 'running', worker_id = :worker, heartbeat_at = :now, started_at = :now
WHERE id = (
  SELECT id FROM job_run
  WHERE state = 'queued' AND lane = ANY(:lanes) AND scheduled_for <= :now
  ORDER BY scheduled_for FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING id, job_key;

-- reap
UPDATE job_run SET state = 'abandoned' WHERE state = 'running' AND heartbeat_at < :older_than;
```

The enqueue goes through the caller's `AsyncSession`, so a use case that writes data and enqueues a job commits both or neither. The adapter is an SQLAlchemy repository like the others; the in-memory sibling keeps a dict and applies the same overlap rules, and both run the shared contract suite.

### 6. Worker, CLI and compose

```python
# entrypoints/cli/worker.py  (driving adapter; thin)
@app.command
async def worker() -> None:
    """Run scheduled and queued jobs."""
    c = build_container()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    await run_worker(c.registry, c.schedules, c.queue, c.reader, c.execute, c.settings, stop)
    # loop: every 60 s -> reap_abandoned, tick; continuously -> claim(lanes) -> execute, heartbeat while running

@job_app.command
async def run(job_key: str) -> None:
    """Run one job now, synchronously, through the same execute wrapper (the "Cron adapter")."""
```

```yaml
# compose.yaml excerpt: a second service from the same image, reusing the existing anchors and volumes
  worker:
    <<: [*hardened, *logging]
    container_name: menagerist-worker
    image: menagerist:local
    command: ["worker"]
    restart: unless-stopped
    environment:
      TZ: ${TZ:-UTC}
      MENAGERIST_DATABASE_URL: postgresql+asyncpg://menagerist:menagerist@postgres:5432/menagerist
    volumes:
      - media-data:/data/media
      - ./backups:/data/backups
    depends_on:
      postgres:
        condition: service_healthy
```

The API service gets the same `TZ`. The worker never migrates; it waits and retries until the schema matches the expected head.

### 7. Settings flow

```python
# platform/config/scheduler.py  (tested, 14 cases)
class SchedulerSettings(MenageristBaseSettings):
    model_config = SettingsConfigDict(frozen=True, validate_default=True, env_prefix="MENAGERIST_",
                                      extra="ignore", env_ignore_empty=True)   # group-local
    timezone: ZoneInfo = Field(default_factory=lambda: ZoneInfo("UTC"),
                               validation_alias=AliasChoices("TZ", "MENAGERIST_TIMEZONE"))
    run_history_per_job: Annotated[int, Tunable()] = Field(
        default=100, ge=1, title="Run history per job", validation_alias="MENAGERIST_SCHEDULER_RUN_HISTORY_PER_JOB")

# platform/config/backup.py  (existing group; one new field, annotation from 2026-10-25-settings-and-config.md)
    schedule: Annotated[CronSchedule, Tunable()] = Field(
        default="0 3 * * *", title="Backup schedule", validation_alias="MENAGERIST_BACKUP_SCHEDULE")
```

`CronSchedule` here is the Pydantic alias `Annotated[str, AfterValidator(check_cron), UIMeta(kind="cron")]` from the layered settings plan (not the domain dataclass in section 3, which is a different type; rename one when implementing). Empty string means off.

```python
# today: ScheduleSource reads settings only
class SettingsScheduleSource:
    def __init__(self, values: Mapping[str, str]) -> None: self._values = values
    async def schedule_for(self, schedule_key: str) -> str | None:
        return self._values[schedule_key] or None

# Phase F of 2026-10-25-settings-and-config.md: same port, backed by SettingsReader (env pin > admin value > default)
class ReaderScheduleSource:
    def __init__(self, reader: SettingsReader) -> None: self._reader = reader
    async def schedule_for(self, schedule_key: str) -> str | None:
        return (await self._reader.get(schedule_key)) or None
```

| Situation | Effective schedule | UI can change it? |
|---|---|---|
| Nothing set | code default | yes |
| Admin saved a value | the admin value | yes |
| Admin saved empty | off | yes |
| `MENAGERIST_BACKUP_SCHEDULE` set | the env value | no (locked) |
| `MENAGERIST_BACKUP_SCHEDULE=` set empty | off | no (locked) |

### 8. Run now

```python
class RunJobNow(CommandHandler[SchedulingUoW, RunJobNowCommand, RunState]):
    access = Requires(SystemPermission.RUN_JOB)

    async def _handle(self, request, actor):
        job = self._registry.get(request.job_key)           # UnknownJob -> 404
        if not job.run_now:
            raise RunNowNotAllowed(job.job_key)
        async with self._uow as repos:
            if (active := await repos.reader.active_run(job.job_key)) is not None:
                return active                                # double click: same run back
            run = await repos.queue.enqueue(NewRun(id=uuid4(), job_key=job.job_key, lane=job.lane,
                                                   scheduled_for=utcnow(), requested_by=actor.id), self._uow)
            await self._uow.commit()
            return run
```

The race between two simultaneous requests is closed by the partial unique index on `(job_key)` for queued and running rows in `skip` and `coalesce` jobs: the loser gets the existing run back.

### 9. A contract test every adapter must pass

```python
@pytest.fixture(params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)])
async def harness(request) -> AsyncIterator[SchedulerHarness]: ...

async def test_coalesce_collapses_a_backlog_into_one_waiting_run(harness):
    harness.register(job("backup.create", overlap=Overlap.COALESCE, lane=Lane.HEAVY))
    for _ in range(3):
        await harness.enqueue("backup.create")
    await harness.drain()
    assert await harness.run_count("backup.create") == 2     # one running at the time of the second call, one coalesced

async def test_same_fire_time_is_never_enqueued_twice(harness): ...   # two ticks, one run
async def test_two_workers_never_claim_the_same_run(harness): ...
async def test_abandoned_run_is_reaped_and_not_retried(harness): ...
```


## Appendix B: event and outbox candidates

The decision on when and why to add events and an outbox is in the plan above (stages 0-4). This is the catalogue behind it.

### Candidates

**Single handler, so stage 1 (enqueue a job in the unit of work):**
- Thumbnails and type checks after upload; deleting the file when a media row is deleted (closes the "row gone, file left behind" gap).
- Data enrichment (TMDB, MusicBrainz, books): a failed lookup must not fail the save.

**Fan-out or cross-module, so stage 2 (in-process domain events):**
- User deletion cleaning settings, media, collections and shares (settings plan Q9: cascade versus event).
- Node-type deletion and purge notifying dependent modules.
- Audit and activity history, including security events (sign-ins, password changes, sessions revoked, API tokens created or revoked, role changes).
- Notifications: backup failed, update available, new device signed in.
- Live UI updates and cache invalidation (a missed push is harmless; clients refetch).

**Outside our database or process, so stage 3 (outbox plus relay):**
- Search and ML indexing sidecars (opt-in, may be down).
- Outbound webhooks and plugins (both on the goals list).

### Caveats to check when revisiting
- At-least-once delivery means idempotent handlers; design event ids and consumer dedupe from the start.
- Decide whether per-aggregate ordering matters (search indexing probably does; notifications do not).
- Retention and replay of processed rows; an admin view for failed events (reuse the scheduler's run history UI).
- Check whether a WebSocket event publisher port exists before designing; the 2026-10-23 repo read did not look for one.

### Open questions for that plan
- One outbox table for all events, or per module?
- Is the audit trail the same store as the outbox?
- Relay delivery: poll, `LISTEN/NOTIFY`, or both?
