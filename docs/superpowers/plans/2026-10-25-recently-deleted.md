# Recently deleted Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let people see what they deleted, restore it, or purge it for good, from a "Recently deleted" page.

**Architecture:** Deletes are already soft (`deleted_at`). Each module gains three use cases for its own content: list deleted, restore, purge. Modules never import each other, so there is no unified endpoint: the page calls the item and collection endpoints and merges the lists in the browser. Purge reuses the hard-delete code written for removing example packs (`System`-only purge use cases), behind a new user-facing use case that only accepts rows already in Recently deleted.

**Tech Stack:** FastAPI, SQLAlchemy on Postgres, SvelteKit 5 runes, shadcn-svelte, Vitest, Playwright.

**Spec:** `docs/DECISIONS.md` ("Removing an example pack purges what it created; exports skip deleted rows (2026-10-23)") and the memory note on the deferred retention purge. No design spec exists beyond the rulings below.

## Global Constraints

- Never create, stage or push commits; the user commits at the checkpoints.
- British English; comments short and factual; the UI never says node, edge or graph (say "item", "connection", "collection").
- `entrypoints → adapters → application → domain`; `graph` and `collections` never import each other.
- `.svelte` and `.svelte.ts` files go through the `svelte-file-editor` subagent. UI follows `frontend/DESIGN_GUIDELINES.md`.
- Subagents: Sonnet 5.5 at medium effort at most; always pass `model` and `effort`.
- Coverage floors: domain, application, shared_kernel 100%; adapters 80%; platform 70%. Every use case sets an access stance and is pinned in the stance tests.

## Rulings made while planning

- **T1 (scope):** version 1 covers items and collections. Connections, item types, relationship types and presets are not in Recently deleted: a connection deleted on its own is rarely worth restoring, and types and presets keep their own lifecycle (their deleted rows keep slugs reusable). Media assets have no `deleted_at`.
- **T2 (restore an item):** clears `deleted_at` and nothing else. Its connections and collection memberships were never touched by the delete, so they reappear. A connection that was deleted on its own stays deleted. If the item's type has been deleted since, restoring is refused with a clear 409 problem (the person must bring the type back first; check whether that is possible today and say so in the report).
- **T3 (restore a collection):** clears `deleted_at`; memberships and a smart collection's definition are unchanged. If restoring would break an existing uniqueness rule (read the collection and item constraints), refuse with a 409 problem naming the clash. No automatic renaming.
- **T4 (purge):** hard-deletes one row that is already in Recently deleted and owned by the caller (or in scope). For an item: its connections (live or deleted, the foreign keys need it), its collection memberships, its attachments, and any media asset and stored file only those attachments used (files go after the commit, as for packs). For a collection: its memberships. A row that is not in Recently deleted is a 404, never purged. Purge is irreversible, so it has its own permission, `graph:item:purge` and `collections:collection:purge`, that are not token-grantable; each implies nothing else.
- **T5 (restore permission):** restore uses the same write permission as delete (`graph:item:write`, `collections:collection:write`), so a token that can delete can restore.
- **T6 (listing):** `GET /node/deleted` and `GET /collection/deleted`, newest deleted first, with the same paging style and `Total-Count` convention as the item list (capped where text search is used), optional `q`. Each row carries what the page needs: id, name, type (items), `deleted_at`. They need the read permission of the resource.
- **T7 (retention):** none. Nothing leaves Recently deleted on its own until the scheduler plan ships a purge job with a retention setting. Exports keep ignoring deleted rows (P2 of the pack-purge decision); a restored-from-export account has no Recently deleted.
- **T8 (empty all):** not in version 1. Purging is one row at a time with a confirmation; a bulk "purge all" can follow once the scheduler's batch purge exists.

## Review Focus

1. Restoring an item brings back its live connections and collection memberships, and not connections deleted on their own.
2. Purge refuses a row that is not in Recently deleted, another account's row, and (for tokens) is refused outright.
3. Purging an item leaves no orphaned edges, memberships, attachments or stored files, and never removes a media asset another item still uses.
4. A restored smart collection still evaluates; one that refers to a collection since purged shows a warning, not an error.
5. The page never shows other accounts' deleted rows, and the deleted lists respect the same scope rules as the normal lists.

---

### Task 1: Items and collections, backend

**Files:**
- Modify: `modules/graph/application` (`list_deleted_nodes.py`, `restore_node.py`, `purge_node.py`), `modules/collections/application` (`list_deleted_collections.py`, `restore_collection.py`, `purge_collection.py`), the matching ports and in-memory and Postgres repositories, both routers (`GET /node/deleted`, `POST /node/{id}/restore`, `DELETE /node/{id}/purge`, and the same for `/collection`; register the fixed paths before `/{id}`), the permission enums and pins (`test_access_stances.py`, `test_permission_mapping.py`), `TOKEN_GRANTABLE_PERMISSIONS` (purge permissions stay out), `shared_kernel` pins if the permission count is pinned
- Test: application tests on in-memory adapters, router tests, Postgres tests under the `integration` marker, architecture tests

**Interfaces:**
- Produces: the six use cases above; response models `DeletedNodeResponse(id, name, type, deleted_at)` and `DeletedCollectionResponse(id, name, kind, deleted_at)`; restore returns the restored resource's normal response; purge returns 204.

- [ ] **Step 1: Failing tests** for each Review Focus line, list ordering and paging, scope (another account), a token actor refused for purge, the 409 cases of T2 and T3, and the openapi docs-versus-behaviour test staying green.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement,** reusing the pack purge use cases for the hard delete; read how `DeleteNode` and `DeleteCollection` guard and commit and do the same.
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, the Postgres tests for the touched repositories, architecture tests; then `poe generate-frontend-client`.

### Task 2: Recently deleted page

**Files:**
- Create (via `svelte-file-editor`): `frontend/src/routes/recently-deleted/+page.svelte`, plus a plain-TS module under `frontend/src/lib/` for merging, sorting and labels
- Modify: the Settings menu or account navigation entry, and the permission checks so Restore and Purge buttons show only with the right permission
- Test: Vitest for the module, Playwright for the flow

**Interfaces:**
- Consumes: Task 1's endpoints and generated client.
- Produces: a page listing deleted items and collections (tabs or a filter, newest deleted first), each row with its name, type, "Deleted <when>", a Restore button, and a Purge button behind the app's confirm dialog ("This permanently deletes <name>. This cannot be undone."). Empty state "Nothing has been deleted." Errors use the app's problem+json pattern; a 409 on restore shows its message.

- [ ] **Step 1: Failing Vitest** for the merge and labels.
- [ ] **Step 2: Implement** the module, then the page through the subagent; lint-frontend, typecheck-frontend, test-frontend; check desktop and phone, light and dark.
- [ ] **Step 3: Playwright:** delete an item, see it in Recently deleted, restore it and see it (with its connection) on the item page again; delete and purge another and see it gone for good; the same for a collection; another account sees nothing of it. Run three times in a row.

### Task 3: Docs and gates

- [ ] **Step 1:** DECISIONS entry for T1 to T8, `backend/README.md` and `frontend/README.md` where they list routes or pages, the memory note updated, the deleted-items line removed from the "known gaps".
- [ ] **Step 2: Full gates:** `poe lint`, `poe typecheck`, `poe test`, `poe coverage`.

**Checkpoint:** user commits.
