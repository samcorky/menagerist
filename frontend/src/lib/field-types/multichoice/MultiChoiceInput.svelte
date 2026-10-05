<script lang="ts">
	import { readPropMeta } from '$lib/schema-meta';
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

	let selected = $derived(
		Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
	);
	let options = $derived.by(() => {
		if (prop.type !== 'array' || !('enum' in prop.items)) return [];
		const e = prop.items.enum;
		return Array.isArray(e) ? e.filter((o): o is string => typeof o === 'string') : [];
	});
	let stale = $derived(selected.filter((v) => !options.includes(v)));
	let variant = $derived(readPropMeta(prop).display);
	// Stale stored values are listed first, as extra selected entries.
	let entries = $derived([
		...stale.map((v) => ({ value: v, label: `${v} (no longer an option)` })),
		...options.map((o) => ({ value: o, label: o }))
	]);

	function toggle(entry: string) {
		const keep = (v: string) => (v === entry ? !selected.includes(v) : selected.includes(v));
		onChange([...stale.filter(keep), ...options.filter(keep)]);
	}
</script>

{#if variant === 'checkboxes'}
	<div role="group" aria-label={ariaLabel} class="flex flex-wrap items-center gap-x-4 gap-y-1">
		{#each entries as entry (entry.value)}
			<label class="flex items-center gap-1.5 text-sm">
				<input
					type="checkbox"
					checked={selected.includes(entry.value)}
					onchange={() => toggle(entry.value)}
					class="h-4 w-4 accent-primary"
				/>
				{entry.label}
			</label>
		{/each}
	</div>
{:else}
	<div role="group" aria-label={ariaLabel} class="flex flex-wrap gap-2">
		{#each entries as entry (entry.value)}
			{@const active = selected.includes(entry.value)}
			<button
				type="button"
				aria-pressed={active}
				class="rounded-full border px-3 py-1 text-sm transition-colors focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none {active
					? 'border-primary bg-primary text-primary-foreground'
					: 'border-input bg-background hover:bg-accent'}"
				onclick={() => toggle(entry.value)}
			>
				{entry.label}
			</button>
		{/each}
	</div>
{/if}
