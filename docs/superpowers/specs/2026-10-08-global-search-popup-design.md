# Global search popup

**Status:** agreed in conversation on 2026-10-08; being implemented.
**Scope:** frontend only. The items list already takes a text query (`q`); nothing changes on the backend.

## Behaviour

- **Open:** `/` opens a search popup from every page, including the items page (where it used to move focus to the page's own search box, which stays for filtering the list in place). A search button in the header opens the same popup, for phones and for people who do not use the keyboard. `Cmd/Ctrl+K` stays quick capture.
- **Use:** one input; results load as you type after a short delay; arrow keys move through the results, Enter opens one, Esc closes the popup and returns focus to where it was before it opened. A hint before typing, a clear "nothing found", and a retry on failure.
- **Results:** items from the existing items search, each with its type, its cover when it has one, and the "Example" badge. A final row, "See all results in Items", sends the query to the items page, where filters and long lists live.
- **Component:** a shadcn-svelte `command` component on bits-ui (already a dependency).

## Decisions

- Items only for now. The popup is built so that adding groups later does not mean a rewrite.
- `/` means one thing everywhere (open the popup); the items page's own box is reached by clicking it.

## Future direction (owner request, 2026-10-08)

Make this a real **command palette and global search over everything**: items, collections, item types, and pages and settings as actions, with **grouped and ranked** results. Open points for that work:

- Collections have no text search on the backend yet (items and item types do).
- Ranking across groups needs a design: a single backend search endpoint that ranks across entities, or a client-side merge of per-entity results with a fixed group order.
- Actions (go to Settings, add an item, install examples) belong in the same list as search results, with a prefix or a mode.
- Recent items and recent searches are natural additions.

## Testing

Pure helpers unit tested; desktop e2e for the keyboard flow (open with `/`, type, arrow, Enter, Esc, focus returns); a phone-width e2e through the header button.
