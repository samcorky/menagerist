<script lang="ts">
	import { Input } from '$lib/components/ui/input/index.js';
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

	function inputType(): string {
		if (prop.type === 'number') return 'number';
		if (prop.type === 'string' && 'format' in prop && prop.format === 'date') return 'date';
		if (prop.type === 'string') {
			const kind = readPropMeta(prop).kind;
			if (kind === 'url') return 'url';
			if (kind === 'email') return 'email';
			if (kind === 'phone') return 'tel';
		}
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
