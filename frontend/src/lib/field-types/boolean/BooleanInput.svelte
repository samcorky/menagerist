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

	let variant = $derived(readPropMeta(prop).display);
	let checked = $derived(value === true || value === 'true');
	let recorded = $derived(
		value === true || value === false || value === 'true' || value === 'false'
	);

	const segment =
		'px-3 py-1 text-sm transition-colors focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none';
</script>

{#if variant === 'checkbox'}
	<label class="flex items-center gap-2">
		<input
			type="checkbox"
			{checked}
			onchange={(e) => onChange((e.target as HTMLInputElement).checked ? 'true' : 'false')}
			class="h-4 w-4 rounded border-input accent-primary"
			aria-label={ariaLabel}
		/>
		<span class="sr-only">{ariaLabel}</span>
	</label>
{:else if variant === 'yes-no'}
	<div
		role="group"
		aria-label={ariaLabel}
		class="inline-flex overflow-hidden rounded-md border border-input"
	>
		<button
			type="button"
			aria-pressed={recorded && checked}
			class="{segment} {recorded && checked
				? 'bg-primary text-primary-foreground'
				: 'bg-background hover:bg-accent'}"
			onclick={() => onChange(recorded && checked ? '' : 'true')}
		>
			Yes
		</button>
		<button
			type="button"
			aria-pressed={recorded && !checked}
			class="{segment} border-l border-input {recorded && !checked
				? 'bg-primary text-primary-foreground'
				: 'bg-background hover:bg-accent'}"
			onclick={() => onChange(recorded && !checked ? '' : 'false')}
		>
			No
		</button>
	</div>
{:else}
	<button
		type="button"
		role="switch"
		aria-checked={checked}
		aria-label={ariaLabel}
		class="inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border border-transparent transition-colors focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none {checked
			? 'bg-primary'
			: 'bg-input'}"
		onclick={() => onChange(checked ? 'false' : 'true')}
	>
		<span
			class="pointer-events-none block size-5 rounded-full bg-background shadow transition-transform {checked
				? 'translate-x-5'
				: 'translate-x-0'}"
		></span>
	</button>
{/if}
