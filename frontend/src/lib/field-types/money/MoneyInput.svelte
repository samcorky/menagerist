<script lang="ts">
	import { Input } from '$lib/components/ui/input/index.js';
	import { NativeSelect, NativeSelectOption } from '$lib/components/ui/native-select/index.js';
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { CURRENCIES } from './currencies';

	let {
		value,
		onChange,
		ariaLabel,
		prop: _prop
	}: {
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	} = $props();

	let current = $derived(
		typeof value === 'object' && value !== null && !Array.isArray(value)
			? (value as Record<string, string>)
			: {}
	);
</script>

<div class="flex flex-1 gap-2">
	<Input
		type="number"
		step="0.01"
		value={current.value ?? ''}
		oninput={(e) => onChange({ ...current, value: (e.target as HTMLInputElement).value })}
		class="flex-1"
		placeholder="0.00"
		aria-label="{ariaLabel} amount"
	/>
	<NativeSelect
		value={current.currency ?? ''}
		onchange={(e) => onChange({ ...current, currency: (e.target as HTMLSelectElement).value })}
		class="w-44"
		aria-label="{ariaLabel} currency"
	>
		<NativeSelectOption value="">- currency -</NativeSelectOption>
		{#each CURRENCIES as c (c.code)}
			<NativeSelectOption value={c.code}>{c.code} - {c.name}</NativeSelectOption>
		{/each}
	</NativeSelect>
</div>
