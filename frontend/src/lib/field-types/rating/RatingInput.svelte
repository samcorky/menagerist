<script lang="ts">
	import { Star } from '@lucide/svelte';
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { MAX_STARS } from './rating';
	import { filledStarClass } from './colour';

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

	let FILLED = $derived(filledStarClass(prop));

	let max = $derived(prop.type === 'number' ? (prop.maximum ?? MAX_STARS) : MAX_STARS);
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
		const next = Math.min(max, Math.max(1, current + step));
		onChange(String(next));
		// Move focus with the selection (roving tabindex).
		(e.currentTarget as HTMLElement)
			.querySelectorAll<HTMLElement>('[role="radio"]')
			[next - 1]?.focus();
	}
</script>

<div
	role="radiogroup"
	tabindex="-1"
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
			<Star class="size-6 transition-colors {n <= shown ? FILLED : 'text-muted-foreground/40'}" />
		</button>
	{/each}
</div>
