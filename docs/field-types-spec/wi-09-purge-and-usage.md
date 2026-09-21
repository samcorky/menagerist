# WI-9: Purge a field's data, with a usage count

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-8. Port methods are listed in `backend-surface.md`.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Spec (proposal).**
- New query: count nodes (or edges, for edge types) of a type whose `attributes` contain a key. New command: remove a key from all nodes of a type. Both go through the repository ports in `graph/ports` (`NodeRepository` and `EdgeRepository`, which already have `count` and `clear_type(type_slug)`), with a SQLAlchemy implementation and an in-memory sibling in `graph/adapters/persistence/`, as the repo requires for every port. Nodes and edges are keyed by `type_slug`, so the handlers resolve the type id to its slug first. JSONB `?` / `-` operators are the natural implementation.
- API endpoints follow the existing router style (see `backend-surface.md` for the exact routes).
- **Authorisation (decided): none for now.** The graph use cases extend the plain `CommandHandler` / `QueryHandler` and enforce no permissions, so the purge stays consistent with them. Add a short `docs/DECISIONS.md` entry: destructive commands such as the purge should check permissions once an authorisation model exists; `AuthorisedCommandHandler`, `AuthorizationPort` and `AllowAllAuthorizationAdapter` are ready when needed.
- **Concurrency (decided): the purge updates each node through the unit of work** (page the nodes that hold the key, remove it, `save`), so `updated_at` and therefore the ETag change. A client holding a stale copy then gets a 412 on its next save instead of writing the purged value back. There is no event publisher or outbox in the code today; the outbox and WebSocket pattern can be added later.
- UI: an archived field shows "Used by N items" with a **Delete data permanently** action behind a confirmation that repeats the count and says what will be lost (it cannot be undone, so §14 calls for a confirmation, not Undo). Use the existing delete-confirmation pattern.
- Open question: should a bulk purge emit per-node outbox/domain events so the planned revision history stays accurate, or a single type-level event? Note: no event publisher or outbox exists in the code today (the relay is parked), so this is moot until one does.

**Tests:** unit tests for the handlers with in-memory repos; one `@pytest.mark.integration` test for the JSONB queries; architecture tests must still pass.


---

## Background (shared by WI-6 to WI-10)


- Editing a node type's `attributes_schema` never touches existing nodes (`update_node_type.py` only saves the type).
- `UpdateNode` validates the **entire** `attributes` dict against the current schema whenever `command.attributes` is not `None`, and the UI sends the full dict on every save. So any schema tightening can block saving an old node, even for fields the user did not touch.
- The backend enforces JSON Schema `required`. Adding a required field therefore makes every existing node of that type fail its next save. This contradicts the design decision that required fields are a soft visual signal that never blocks saving.
- Removing a field from the schema leaves its data in the JSONB (there is no `additionalProperties: false`). The attributes editor then shows the orphaned value under "Additional details", labelled with the raw UUID key. Re-adding the field creates a new UUID, so the old data does not reattach (WI-20 changes this: a re-added field with the same title gets the same readable key and reattaches).
- Schemas are shared instance-wide, so a type edit affects every node of that type.
