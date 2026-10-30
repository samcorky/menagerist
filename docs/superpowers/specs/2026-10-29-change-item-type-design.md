# Changing and clearing an item's type

Date: 2026-10-29. Status: plan for review. Follows the type picker work, which deliberately left this out.

## Problem

An item's type can be set once. `Node._apply_type` raises "type cannot be changed after it is set", `UpdateNode` treats `type: None` as "leave alone", and the UI hides the picker once a type exists. A wrong choice (or a type later renamed or reorganised) is permanent, which makes the type picker's "Create X" row risky and the shared catalogue hard to tidy.

## What already exists (verified in code)

- Types are one shared catalogue, not per person (`NodeType` has no owner). Creating one is open to anyone who may write items.
- `DeleteNodeType` already clears the type from affected items via `NodeRepository.clear_type` and **keeps their `attributes`**. So "an item whose attribute values have no matching schema" is an existing, supported state.
- Attributes are validated against `merge_attribute_schemas(type_schema, node.extra_schema)` only when `attributes` is in the request. The type is not re-validated on its own.

## Goals

1. Change an item's type to another type, or to none, from the item page.
2. Never lose data silently.
3. Keep the one API: no new endpoint, same `PATCH /node/{id}`.

## Non-goals

- Bulk retyping, per-person types, or the wider "rethink global types" (see Open question 2).
- Converting values between field kinds.

## Design

**Rule: values are kept, not converted.** Changing the type changes which schema describes the values. Values whose key exists in the new schema with a compatible kind show as normal fields. Values with no home are kept in `attributes` and shown in an "Other values" block (read-only, each with a "Remove" action and a one-click "Keep as an item field", which uses the existing `extra_schema` overlay and `promote_extra_schema_field`). Nothing is deleted by retyping.

**API.**
- `type` in `PATCH /node/{id}`: a slug sets or changes it; `null` clears it (the same convention as type `icon` and `colour`); a blank string is an error; omitted leaves it. `UpdateNodeCommand` and `Node.update` follow; `_apply_type` loses the once-only rule. A type slug that does not exist is still created on the fly (current behaviour), so the picker's Create row keeps working.
- No validation of existing `attributes` against the new schema at change time (they may legitimately not fit). They are validated on the next edit that sends `attributes`, as today.
- Update the OpenAPI text (`UpdateNodeRequest.type`), the 422 message is removed, `docs/DECISIONS.md` gets an entry.

**UI.**
- The item page header shows the type as a chip that opens the same `TypePicker` (with "No item type" enabled). Choosing a different type shows a confirm dialog only when some values would end up in "Other values", listing them and saying nothing is deleted; otherwise it applies at once with an undo toast (design guideline §14: undo over confirm).
- "Other values" block under the details card, as above.
- `TypePicker` on the item page passes `allowClear` and no longer hides after first use.

## Order of work (TDD, each step test first)

1. Domain: `Node.update(type="")` clears, changing works, once-only tests flipped (`tests/modules/graph/domain/test_node*.py`).
2. Application: `UpdateNode` clear/change, unknown slug still auto-created, attributes untouched on retype (`test_update_node.py`).
3. API: router tests for set, change, clear, omit; regenerate client; OpenAPI examples.
4. Frontend logic: pure function `orphanedValues(attributes, newSchema, extraSchema)` in `src/lib` with unit tests.
5. Item page: type chip + picker, confirm only when orphaned values exist, undo toast, "Other values" block; e2e: change type keeps values, clear type, undo, promote orphan to item field.
6. Docs (DESIGN_GUIDELINES §9a/§10, DECISIONS), full gates, full e2e.

Estimate: backend small (a rule removed plus an empty-string convention), frontend the larger half.

## Open questions (my defaults in bold)

1. Is "keep orphaned values, show them under Other values" right, versus **(default)** that, or refusing the change when values would not fit, or deleting them? Keeping is the only option that cannot lose data and matches what type deletion already does.
2. Should this wait for the wider global-types rethink? **Default: no.** Retyping is needed whichever way global types go (shared or per person), and it adds no new coupling to the catalogue.
3. Should changing type be recorded anywhere (activity log)? **Default: no**, there is no item history today.
