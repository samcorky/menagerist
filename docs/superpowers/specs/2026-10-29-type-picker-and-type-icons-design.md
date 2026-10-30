# Type picker, cover placeholder and per-type icon and colour

Date: 2026-10-29. Status: agreed in conversation (picker: "yeah"; cover placeholder: "whatever is best"; icon and colour requested by the user). Defaults below are my calls and can be changed.

## Intent

Choosing an item type is clumsy: three places show a wall of pills (the item page, the new-item form, Quick capture), the list includes every shared type, creating a type in Quick capture opens a second mini form, and the item page only offers a type while the item has none. Items with no cover look empty. Types should be recognisable at a glance with their own icon and colour.

## Goals

- One searchable type picker everywhere a type is chosen, built on the existing `ui/combobox` (not a new widget): type to filter, keyboard friendly, a clear "no type" choice, types you use listed first under "In use" (from `GET /node/count/types`), the rest under "Other item types", and a `Create "X"` row when the text matches no type (one Enter creates and selects it, in Quick capture too).
- Each item type can have a default Lucide icon and a colour, set in the type editor dialog, shown wherever a type or a cover-less item is shown.
- Item page without a cover: the left column holds a placeholder (the type's icon and colour, with "Add a photo" drop or browse that sets the cover). Grid and Home tiles use the same placeholder.

- **Randomise icon and colour:** a dice button beside the icon and colour fields in the type editor picks a random icon from the curated set and a random palette colour in one click (undoable by picking again or clearing).
- **Surprise me:** a button on Home and on collection pages that opens a random item. It respects where you are: on Home any of your items, on a collection that collection's items. It needs a small backend endpoint (`GET /api/v1/node/random`, same filters as the item list, 404 when nothing matches) because the item list pages by cursor and cannot jump to the n-th item.

## Non-goals

- Changing or clearing an item's type after it is set. The API rule "`type` may only be set once" stays; lifting it needs a separate backend design (what happens to values the new type has no field for) and is part of the open global item types rethink.
- No per-item icon or colour, and no free hex colours.
- No change to example packs (they have no icons yet; they can opt in later).

## Decisions

1. **Backend fields.** `NodeType` gains `icon: str | None` (a Lucide icon name in kebab case, at most 64 characters, shape checked only: `[a-z][a-z0-9]*(-[a-z0-9]+)*`) and `colour: str | None` (one of a fixed palette key: `gray`, `red`, `orange`, `amber`, `green`, `teal`, `blue`, `violet`, `pink`). Shared theme-aware palette keys rather than hex values keep dark mode and contrast correct. Create takes both optionally; update leaves omitted fields unchanged and `null` clears one (a blank string is an error). One nullable column each in `node_types` (migration); responses always include both. The backend does not know which icon names exist; the frontend shows its known set and falls back to the generic package icon for any name it does not know.
2. **Icons are a curated set.** `src/lib/type-icons.ts` maps about 120 collector-relevant Lucide names (film, music, book, gamepad, disc, camera, shirt, watch, palette, car, trophy and so on) to components, so the bundle only holds those. The picker searches that set by name and keywords. Importing all 1,500 icons would add hundreds of chunks to the image for little gain; the set is a one-file list that is easy to extend.
3. **Colours** map palette keys to token-based classes with dark-mode variants in `src/lib/type-colours.ts`; a `TypeIcon` component renders icon plus colour from a type, with the generic package icon in the neutral tone as the fallback.
4. **Where shown.** Settings > Item types rows, the type picker rows, the cover placeholder (item page, grid tiles, Home), and the item page header beside the type label.
5. **Picker.** `src/lib/components/type-picker.svelte` replaces `category-select.svelte` in `items/new`, Quick capture and the item page (shown while an item has no type). It loads types once (`loadItemTypes`) and in-use counts once per open; creating calls `createNodeType` with the typed label and selects the result.
6. **Cover placeholder.** The item page's cover column renders the placeholder when there is no cover. The "Add a photo" action reuses the Files card's existing upload and set-cover logic rather than a second upload path.

## Order of work

1. Backend: domain, migration, use cases, API, tests, regenerate the client. 2. Frontend: icon and colour modules and `TypeIcon`. 3. Icon and colour fields in the type editor dialog; show in the types list. 4. The type picker and its three call sites. 5. Cover placeholder and tile placeholders. 6. Randomise icon/colour button. 7. Backend `GET /node/random` and the Surprise me buttons. 8. Docs, full gates, e2e.
