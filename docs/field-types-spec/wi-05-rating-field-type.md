# WI-5: Rating field type

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-14 and WI-20. WI-2 must land before rating is offered as a group sub-field.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


Prototype built and verified in a scratch clone (field-type tests pass, svelte-check clean on the touched files). Reimplement it in the repo from the reference below.

**Design.**
- **Do WI-14 first.** The reference code below was prototyped before WI-14 and marks the field with a flat `x-rating: true`. When implementing, drop that marker: store `minimum: 1`, `maximum: 5`, `multipleOf: 1` plus `x-menagerist.kind: 'rating'`, and have `fromSchema` match on the kind through the WI-14 accessor. The rest of the design is unchanged.
- Stored as a JSON number with `minimum: 1`, `maximum: 5`, `multipleOf: 1` (the flat `x-rating: true` marker in the code below is superseded by WI-14). Using `type: 'number'` keeps the existing `rowsToAttributes` coercion working, and an unset rating is simply omitted. The backend ignores the unknown keyword, like `x-multiline`.
- **Registration order matters.** `rating` must be imported before `number` in `field-types/index.ts`, because both match `type: 'number'` and the first match wins. Leave a comment saying so. WI-12 (optional) removes this footgun by ranking matches instead of relying on import order.
- `canBeSubField: false` for now. A blank group cell becomes `0` (WI-2), which fails `minimum: 1`. After WI-2 lands, flip it to `true` and add a test.
- Star count is fixed at 5. Making it configurable is part of WI-11.

**Interaction (input widget).**
- Five stars in a row, `role="radiogroup"` with `role="radio"` buttons.
- Hover previews: the hovered star and all before it fill with the accent colour; leaving the row snaps back to the saved rating. Stars scale slightly on hover.
- Click sets the rating; clicking the current rating clears it (`onChange('')`, which `rowsToAttributes` omits for numbers).
- Keyboard: roving `tabindex`, arrow keys change the rating and move focus, focus shows the same preview as hover.
- Touch: no hover, tap to set.
- Accent is currently amber (`fill-amber-400 text-amber-400`). Swap to `fill-primary text-primary` if the theme accent is wanted. Keep it in one place.

**View widget.** Read-only stars, `role="img"` with `aria-label="N out of 5 stars"`, or `—` when empty.

**Reference implementation.**

`frontend/src/lib/field-types/rating/rating.ts`
```ts
import { register } from '../registry';
import RatingInput from './RatingInput.svelte';
import RatingView from './RatingView.svelte';

export const MAX_STARS = 5;

register({
	kind: 'rating',
	label: 'Rating',
	// A blank group cell is coerced to 0 by rowsToAttributes, which would fail `minimum: 1`.
	canBeSubField: false,
	toSchema: (f) => ({
		title: f.label,
		type: 'number',
		'x-rating': true,
		minimum: 1,
		maximum: MAX_STARS,
		multipleOf: 1
	}),
	fromSchema: (key, prop, required) =>
		prop.type === 'number' && 'x-rating' in prop && prop['x-rating'] === true
			? { key, label: prop.title, kind: 'rating', required, options: [], subFields: [] }
			: null,
	InputWidget: RatingInput,
	ViewWidget: RatingView
});
```

`frontend/src/lib/field-types/rating/RatingInput.svelte`
```svelte
<script lang="ts">
	import { Star } from '@lucide/svelte';
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let {
		value,
		onChange,
		ariaLabel,
		prop
	}: {
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	} = $props();

	let max = $derived(prop.type === 'number' && 'maximum' in prop ? prop.maximum : 5);
	// Rows hold strings ('' when unset); API values arrive as numbers.
	let current = $derived(value === '' || value == null ? 0 : Number(value) || 0);

	// Star under the pointer/focus; 0 when idle. Drives the live preview.
	let hovered = $state(0);
	let shown = $derived(hovered || current);

	function select(n: number) {
		// Clicking the current rating clears it. '' is omitted by rowsToAttributes for numbers.
		onChange(n === current ? '' : String(n));
	}

	function onKeydown(e: KeyboardEvent) {
		const step =
			e.key === 'ArrowRight' || e.key === 'ArrowUp'
				? 1
				: e.key === 'ArrowLeft' || e.key === 'ArrowDown'
					? -1
					: 0;
		if (step === 0) return;
		e.preventDefault();
		const next = Math.min(max, Math.max(1, (current || 0) + step));
		onChange(String(next));
		// Move focus with the selection (roving tabindex).
		(e.currentTarget as HTMLElement)
			.querySelectorAll<HTMLElement>('[role="radio"]')
			[next - 1]?.focus();
	}
</script>

<!-- svelte-ignore a11y_interactive_supports_focus -->
<div
	role="radiogroup"
	aria-label={ariaLabel}
	class="flex flex-1 items-center gap-0.5"
	onmouseleave={() => (hovered = 0)}
	onkeydown={onKeydown}
>
	{#each Array.from({ length: max }, (_, i) => i + 1) as n (n)}
		<button
			type="button"
			role="radio"
			aria-checked={n === current}
			aria-label="{n} {n === 1 ? 'star' : 'stars'}"
			tabindex={n === (current || 1) ? 0 : -1}
			onclick={() => select(n)}
			onmouseenter={() => (hovered = n)}
			onfocus={() => (hovered = n)}
			onblur={() => (hovered = 0)}
			class="cursor-pointer rounded p-0.5 transition-transform hover:scale-110 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
		>
			<Star
				class="size-6 transition-colors {n <= shown
					? 'fill-amber-400 text-amber-400'
					: 'text-muted-foreground/40'}"
			/>
		</button>
	{/each}
</div>
```

`frontend/src/lib/field-types/rating/RatingView.svelte`
```svelte
<script lang="ts">
	import { Star } from '@lucide/svelte';
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let { value, prop }: { value: unknown; prop: JsonSchemaProperty } = $props();

	let max = $derived(prop.type === 'number' && 'maximum' in prop ? prop.maximum : 5);
	let current = $derived(value === '' || value == null ? 0 : Number(value) || 0);
</script>

{#if current > 0}
	<span
		class="inline-flex items-center gap-0.5"
		role="img"
		aria-label="{current} out of {max} stars"
	>
		{#each Array.from({ length: max }, (_, i) => i + 1) as n (n)}
			<Star
				class="size-4 {n <= current ? 'fill-amber-400 text-amber-400' : 'text-muted-foreground/40'}"
			/>
		{/each}
	</span>
{:else}
	<span>—</span>
{/if}
```

`frontend/src/lib/field-types/index.ts`: add `import './rating/rating';` immediately after the `date` import, with the ordering comment.

`frontend/src/lib/schema-types.ts`: add this variant to `JsonSchemaProperty`, before the plain number variant:
```ts
| { title: string; type: 'number'; 'x-rating': true; minimum: 1; maximum: number; multipleOf: 1 }
```

**Tests** (`tests/field-types.test.ts`): rating wins over number in `descriptorForProp`; a plain number is not captured; `toSchema(fromSchema(...))` round-trips. Add `rating` to `EXPECTED_KINDS`.

**Docs:** add a section to `docs/field-types.md` and a `DECISIONS.md` entry (rating stored as a constrained number; registration-order rule).
