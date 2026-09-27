# WI-26: Money field kind (number + currency)

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-14 (`x-menagerist.kind`), WI-1 (empty-value omission pattern), the `quantity` kind's (WI-24) `coerceObjectValue`/`coerceGroupRow` sub-field infrastructure in `attribute-rows.ts`, which this kind reuses directly rather than re-deriving.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.
> **Status:** proposed, not yet implemented. Promoted from `further-field-types.md`'s "Money" candidate row on direct request.

**Motivating case.** Purchase price, insured value, sale price - "£45.00", "$120.50". Structurally the same shape as `quantity` (a number plus a short qualifier, entered and displayed together), but two real differences justify its own kind rather than a `quantity` display variant: the qualifier is a **closed set** (currency codes), not free text, and the view format is currency-conventional (`"£45.00"`, two decimals, symbol prefixed) rather than `quantity`'s `"{value} {unit}"`.

**Stored as** a small object, the same pattern as `quantity`:

```json
"purchase_price": {
  "title": "Purchase price",
  "type": "object",
  "properties": {
    "value": { "type": "number" },
    "currency": { "type": "string" }
  },
  "x-menagerist": { "kind": "money" }
}
```

A value is `{"value": 45, "currency": "GBP"}`. Both parts are independently optional (a bare amount with no currency chosen yet, or a currency chosen with no amount typed yet, are both legitimate half-filled states, matching `quantity`'s own rule); an empty object is valid and must be omitted rather than saved (WI-1).

**Currency input (decided): a fixed dropdown of the full ISO 4217 list.** Unlike `quantity`'s deliberately-loose free-text unit (units are open-ended; currencies are not), currency is a closed, well-known set - a `<select>`/combobox of all ~180 active ISO 4217 codes, each shown as `"GBP - British Pound"` (code plus common name) with the code stored. The list ships hardcoded in `field-types/money/currencies.ts` (a plain data file, not a WI-19c `choice_list` preset - it is not user-editable, and every money field on every type shares the identical list, so a preset's per-type-copy-with-provenance machinery buys nothing here). No default selection; an unset currency is a valid partial state.

**Sub-field use (decided): supported from v1**, unlike `quantity`'s deferred v1 scope - the object-cell infrastructure `quantity` needed (`GroupRow` widened to `Record<string, string | Record<string, string>>`, `coerceObjectValue`/`coerceGroupRow` in `attribute-rows.ts`, `canBeSubField: true` wiring in `GroupExtras.svelte`) already exists and is exercised by `quantity` and `choice` today (see `docs/DECISIONS.md`'s "Quantity and choice as table sub-fields" entry). `money` reuses that same path directly: `canBeSubField: true` from the start, its own `GroupExtras`-equivalent entry (a currency-dropdown cell renderer) alongside `quantity`'s.

**In the app.**
- **Entering:** a number input and the currency combobox side by side, sharing one field row (top-level) or one table cell (sub-field) - same layout precedent as `quantity`'s number-plus-text pair.
- **Viewing:** the amount formatted to two decimals with the chosen currency's symbol prefixed when the symbol is known (`"£45.00"`), falling back to `"{value} {currency code}"` (`"45.00 XYZ"`) for a currency with no common symbol in the hardcoded list; just the amount when no currency is set; just the currency code when no amount is set; `-` when the whole field is empty, matching every other empty-field convention in this spec.
- **Highlights (WI-16):** highlightable; `formatSummary` renders the same formatted string as the view.
- **Search (WI-17):** same open question `quantity`'s spec flagged and left unresolved - confirm whether the existing search implementation recurses into an object value's `value`/`currency` or only scans top-level scalars and group rows; if not, `money` needs the same extension `quantity`/`location` would.
- **No currency conversion, ever.** A money value is one amount in one currency; there is no exchange-rate lookup, no multi-currency total, no "convert to my default currency" anywhere in this spec. Two money fields with different currencies are simply not comparable by this app - that is a correct, deliberate limitation, not a gap.
- **Sorting/filtering by amount:** out of scope for v1, same call `quantity` made.

**Backend:** nothing new beyond registering the kind conceptually - no port, no new validation keyword, no migration. Plain JSON in the existing `attributes`/`attributes_schema` column, same as `quantity`.

**Acceptance.**
- A money field round-trips `{value, currency}` through `toSchema`/`fromSchema` unchanged.
- Entering only an amount, or only a currency, saves that partial value; entering neither omits the key entirely.
- A money field works as a group (table) sub-field from v1: adding a "Price" column to a table produces a per-row amount-plus-currency cell, using the same `coerceObjectValue`/`coerceGroupRow` path `quantity` and `choice` already exercise.
- The currency dropdown lists the full ISO 4217 set; picking one stores its three-letter code, never the display name or symbol.
- View mode shows a two-decimal, symbol-prefixed amount for a known-symbol currency, and degrades gracefully (code suffix) for one without a symbol in the hardcoded table.

**Tests.** Unit: `toSchema`/`fromSchema` round-trip (both parts, value-only, currency-only, explicit-kind-only matching); the empty/partial-value omission in `attributesToRows`/`rowsToAttributes`, both top-level and as a group sub-field; `formatSummary`/view-format output for each non-empty state including the no-symbol fallback. Contract fixture: add a money example (for instance a "Purchase price" field) to `example-node-type-schema.json`, matching how `weight`/`my_rating` already serve that role for their kinds.
