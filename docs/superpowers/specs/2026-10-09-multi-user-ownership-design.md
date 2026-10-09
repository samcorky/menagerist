# Multi-user: accounts, ownership and sharing

**Status:** design agreed in conversation on 2026-10-09; awaiting written-spec review. No code yet.
**Scope:** staged. Stage 1 (accounts and private ownership) is specified in full. Stage 2 (sharing) is specified at the level needed to keep Stage 1 compatible. Stage 3 items are listed, not designed.
**Closes:** the precondition recorded in `docs/DECISIONS.md` ("Collection ownership is stored but not enforced: a precondition for multi-user") and replaces the "AllowAll authorization adapter in v1" decision once Stage 1 ships.

## Purpose

Menagerist is single-user today: one fixed actor, an `AuthorizationPort` that permits everything, and an `owner_id` stored only on collections. The goal is a server several people can use, where content is **private to its owner by default** and can later be **shared with chosen people**, without one person ever seeing or changing another's content by accident.

## Decisions (owner, 2026-10-09)

1. **Model:** private by default, shareable per collection or per item (option 3 of the original three).
2. **What is owned:** content (items, connections, files, collections) is owned. Structure (item types, relationship types, presets) is shared by everyone on the server. Restricting who may edit shared structure is a later change; in Stage 1 everyone may.
3. **Sharing:** with chosen people at two levels, can view and can edit. Only the owner may delete, re-share or change access. Groups come later. A public "anyone with the link" option may come later; the access check treats an anonymous visitor as an ordinary kind of actor so it can be added without rewriting the checks.
4. **Sign-in:** local accounts first (username or email plus password). OIDC is added later as a second way to sign in alongside local accounts, not as a single-sign-on-only mode. Sign-in sits behind one port in an `identity` module so a second adapter does not touch the rest.
5. **Staging:** (1) accounts and private ownership, enforced everywhere; (2) sharing with people; (3) later: groups, public link, OIDC, restricting who may edit shared types.
6. **Existing data:** the first admin created on an upgraded server adopts everything already there.
7. **Enforcement point:** the application layer: `AuthorizationPort` for single-entity actions and a "visible to this actor" filter inside the repositories for every list, search and count. Not Postgres row-level security, and not route-level checks alone.

## Stage 1: accounts and private ownership

### Identity module

- New `identity` module: users (id, username or email, password hash, role admin or member, created time) and sessions.
- Passwords use a modern slow hash (argon2). Sessions are secure, HTTP-only cookies with CSRF protection (the frontend is a same-origin single-page app).
- The first account on an empty server becomes the admin through a setup screen. After that the admin invites people; open sign-up is off.
- A sign-in port with a local-account adapter. `get_current_actor` reads the session and returns a real `Actor`; `AuthorizationPort` stops being allow-all. The system actor remains for background jobs and the CLI.

### Ownership

- Items, connections, files and collections each carry an `owner_id` (collections already do). Item types, relationship types and presets stay shared.
- A connection exists only between items the actor can see and follows its items: it is visible to people who can see both ends.
- In Stage 1 everything is private, so the owner is always the creator. "Who made it and who changed it" is deliberately left to Stage 2 (below); existing rows are attributed to the first admin anyway, so nothing is lost by waiting.

### The access rule (Stage 1, private only)

- An actor can see an entity if they own it. An admin has no special view of other people's content.
- Every list, search (`q`), count, `GET /node?collection=`, the collection membership bridge, example installs and status counts are filtered by "visible to this actor" inside the repositories.
- Single-entity reads, edits and deletes check ownership and answer 404 for something the actor cannot see, so existence is not revealed.

### Things that need care

- ETags and cached lists must be per viewer. An item count that feeds an ETag must be the count the actor can see.
- Example packs install content owned by the installing user, with shared types. Removal and re-adoption only touch the installer's own things.
- Files are served only to actors who can see the item that owns them.
- Slugs: collection slugs are unique among live collections today. Per-owner uniqueness is decided when this lands (see the earlier "Not decided" note in DECISIONS.md).

### Existing data

A migration adds `owner_id` to the content tables. The first admin created on an upgraded server adopts every existing item, file, connection and collection (including collections owned by the old fixed actor) in a one-time claim at setup. Nothing is lost or hidden.

### Frontend

A sign-in page, a first-run setup page, an invitation flow for the admin, a signed-in indicator with sign out, and a redirect to sign in when a session expires. UI words stay "item" and "collection"; never node, edge, graph or shelf.

## Stage 2: sharing (compatible shape, designed later)

- A share record: entity, recipient (a user, or "everyone on this server"), level (view or edit).
- Visibility becomes: you own it, or it was shared with you directly, or it is in a **manual** collection shared with you. The filter lives in the repositories, so Stage 1 code does not change shape.
- Sharing a manual collection grants access to its items through that collection only; removing an item from the collection removes the access.
- Provenance (`created_by_id`, `updated_by_id`) ships with this stage; see below.

### Who made and who changed it (follow-up, with sharing)

Once people can edit each other's items, and because shared types can be edited by anyone, the application should record who did what. Three separate things, kept apart:

- `owner_id`: who controls the entity and may share or delete it. It can change (for example if ownership is transferred).
- `created_by_id`: who made it. It never changes; it is provenance, not permission.
- `updated_by_id`: the last person who changed it, set beside `updated_at`.

`created_by_id` and `updated_by_id` are then added to every entity that has `created_at` and `updated_at`: the content (items, connections, files, collections) and the shared structure (item types, relationship types, presets). Shared structure matters most, because in Stage 1 everyone may edit it. The domain methods that already set timestamps take the actor and set these too. Content from an example install records the person who installed it; background jobs and the CLI record the system actor, shown as "System". If a user is later deleted, the ids stay and the UI shows "a former member".

The item page shows it quietly ("Added by Sam, last edited by Alex"), and only on a server with more than one user. Names of who added or edited something become visible to other people who can see that entity, so usernames are not private within a server; that is normal for a shared household server.

## Stage 3 and later

Groups, the public "anyone with the link" option, OIDC sign-in, restricting who may edit shared types, and a full **activity log** (entity, actor, action, time, a summary of the change) for "who edited this and what changed". The actor already flowing through every write in Stage 1 makes the log an additive change.

## Dynamic collections (not built; constraint on the design)

A dynamic collection is a stored rule plus an owner; its members are computed by running the rule as an ordinary item query.

- The rule runs for the **viewer**, through the same "visible to this actor" filter as every other list. Sharing a dynamic collection shares the rule, not access to items: a viewer sees only matching items they can already see. Nothing leaks.
- Unlike a manual collection, **membership of a dynamic collection grants no access**. Otherwise a rule such as "everything tagged holiday" could expose items the owner never meant to share, and items would enter and leave the shared set silently as they are edited. To share a result set with access, the owner converts it to a manual snapshot or shares the items directly (a later feature).
- Counts and ETags for a dynamic collection are per viewer.
- Putting the visibility filter in the repositories, not in collection code, is what makes all of this free.

## Known issue carried to Stage 2: per-person item state

Flags such as "favourite" (and possibly tags) are stored once on the item. Once items are shared, "my favourite" must not be everyone's. Stage 2 decides which state is per person. Irrelevant in Stage 1, where everything is private.

## Testing

- A generated check over all routes: user B gets 404 or an empty list for user A's content on every route that returns or changes content, so a new route cannot forget enforcement.
- An architecture test that every repository list/search/count method takes the visibility scope.
- (Stage 2) `created_by_id` is set once and never changes; `updated_by_id` follows every change, including by the system actor; a deleted user's ids survive.
- Unit tests for the identity module (hashing, session expiry, invite flow, first-admin setup, closed sign-up) and for the migration's claim step.
- E2E: first-run setup, sign in and out, invite a second user, the second user sees none of the first's content, search and counts are per user, expired session redirects.
