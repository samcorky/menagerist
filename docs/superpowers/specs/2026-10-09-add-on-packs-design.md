# Add-on example packs and cross-pack links

**Status:** design agreed in conversation on 2026-10-09; awaiting written-spec review. No code yet.
**Scope:** Stage 1 (add-on packs with `requires` and `pack:ref` references, including multi-pack "bridge" add-ons) is specified in full. Stage 2 (optional links that appear automatically when two packs are both installed) is specified in outline.
**Builds on:** `2026-10-06-example-packs-design.md`, format v2 (collections) and v3 (covers), and the re-adoption rule in `docs/DECISIONS.md`.

## Purpose

Today every example pack is self-contained. Some content naturally builds on another pack ("Board games extras" needs the base games and their publishers), and some content only makes sense when two packs are both present (a soundtrack record that belongs to a film). Packs should be able to say so, and to connect to each other's items, without the people using them managing dependencies by hand.

## Decisions (owner, 2026-10-09)

1. An **add-on** adds content that uses its required packs' types and items (new items, connections, collections). It never changes a required pack's types or items (option A).
2. `requires` is a **list**, so a "bridge" add-on can require two or more packs and consist mostly of connections between their items. Connections between packs are therefore ordinary add-ons.
3. **Removal is blocked**, not cascaded: a pack cannot be removed while an add-on that requires it is installed; the message names what to remove first.
4. **Order of work:** `requires` and cross-pack references first; optional automatic links (Stage 2) reuse the same reference lookup afterwards.

## Stage 1: add-ons with `requires`

### Pack format

- Pack format **version 4** (additive; versions 1 to 3 still load) adds an optional top-level `"requires": ["games", ...]`: distinct, existing pack ids, never the pack's own id. A pack with `requires` is an **add-on**.
- Anywhere a pack refers to an item type, relationship type or item by `ref` (an item's `type`, a connection's `from`, `to` and `type`, a collection's `items`), an add-on may write `"<pack-id>:<ref>"` to refer to something a **required** pack created. The prefix must be one of this pack's `requires`; a prefix not listed, an unknown ref format or a self-reference is a parse error. Whether the ref exists in the required pack's file is checked at catalogue load (below).
- An add-on may define its own item types, relationship types, items, connections and collections as before. It may not define a slug that the required pack defines (the existing slug-clash check covers this at install).
- Presets are not referenceable across packs.

### Catalogue checks (load time)

Every `requires` id exists in the catalogue; no cycles (a chain of add-ons must end at packs with no `requires`); every `pack:ref` points at something the named pack's file defines, of the right kind. Violations fail loudly when the catalogue loads, so a bad shipped pack is caught in tests.

### Install

- Refused with a 409 ("Add *Board games* first") if any required pack has no active, finished installation.
- The install resolves each `pack:ref` through the required pack's installation record: the entity recorded for that `(kind, ref)` that the required pack still owns. If the person has since deleted or replaced that entity, the install is refused naming the missing item ("*Board games* no longer has *Lantern Harbour*"), not silently skipped.
- Everything the add-on creates is recorded in the add-on's own installation, so removal, kept-entity handling, covers and re-adoption work as they do today. Counts show only what the add-on itself creates.

### Removal

- Removing a pack that an installed add-on requires is refused with a 409 naming the add-on(s) ("Remove *Board games extras* first").
- Removing the add-on is the normal flow. Its connections to the required pack's items go first (they are the add-on's own); an edited connection is kept under the existing rule and then counts as the person's data on the base item, so a later removal of the base pack keeps that item.

### API and UI

- The pack list response gains `requires` (ids) and, per pack, the installed packs that depend on it (`required_by`), so the page can explain disabled buttons without extra calls.
- The Examples page marks an add-on ("Needs *Board games*"), disables its Add button with that reason until the required packs are installed, and disables Remove on a pack with dependants, with the reason beside it. Disabled controls keep the 44 px touch-target rule and are explained in text, not only by greying out.
- An add-on's card sits with its base visually only by wording; no new layout.

### Shipped examples

Two small add-ons prove the mechanism and are content, not code:
- **Board games extras** requires `games`: a few more games and an expansion, connected to the base pack's publishers and added to one new collection.
- **Soundtracks** requires `music` and `movies`: a handful of connections between films and records. Names are fictional (checked against real titles).

## Stage 2 (outline): optional links

A pack may declare `links` to another pack: "if *Movies* is installed, also connect these of my items to these of its items". The links exist whenever **both** packs are installed, whichever is added second, and are removed before either pack is removed, so removal is never blocked for links. Links are recorded under the installation of the pack that declares them; installing the second pack applies the pending links of the first. Edited links are kept under the existing rule. This reuses the Stage 1 reference lookup and the requirement that a referenced entity still exists.

## Testing

- Parser: `requires` and `pack:ref` accepted and rejected as above, versions 1 to 3 unchanged.
- Catalogue: unknown required pack, cycle, dangling cross-pack ref, wrong kind.
- Install/uninstall with in-memory targets: refused without the base; resolved refs create the right connections; deleted base item refuses with the item named; base removal blocked and unblocked after the add-on goes; edited connection kept; counts exclude cross-pack things; re-adoption of an add-on's kept entities; a failed add-on install leaves the base untouched.
- API: `requires` and `required_by` in the list, 409 bodies.
- E2E: add-on disabled until base installed, install both, connections visible on a base item, base removal blocked with the reason, remove the add-on then the base.
