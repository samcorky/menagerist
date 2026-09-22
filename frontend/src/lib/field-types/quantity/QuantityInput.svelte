<script lang="ts">
	import { Input } from '$lib/components/ui/input/index.js';
	import type { JsonSchemaProperty } from '$lib/schema-types';

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
		value={current.value ?? ''}
		oninput={(e) => onChange({ ...current, value: (e.target as HTMLInputElement).value })}
		class="flex-1"
		placeholder="180"
		aria-label="{ariaLabel} value"
	/>
	<Input
		type="text"
		value={current.unit ?? ''}
		oninput={(e) => onChange({ ...current, unit: (e.target as HTMLInputElement).value })}
		class="w-24"
		placeholder="unit"
		aria-label="{ariaLabel} unit"
	/>
</div>
