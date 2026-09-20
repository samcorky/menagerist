<script lang="ts">
	import { Input } from '$lib/components/ui/input/index.js';
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

	function inputType(): string {
		if (prop.type === 'number') return 'number';
		if (prop.type === 'string' && 'format' in prop && prop.format === 'date') return 'date';
		return 'text';
	}
</script>

<Input
	type={inputType()}
	value={typeof value === 'string' || typeof value === 'number' ? String(value) : ''}
	oninput={(e) => onChange((e.target as HTMLInputElement).value)}
	class="flex-1"
	aria-label={ariaLabel}
/>
