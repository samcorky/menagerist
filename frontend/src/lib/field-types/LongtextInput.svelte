<script lang="ts">
	import { Textarea } from '$lib/components/ui/textarea/index.js';
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
</script>

<Textarea
	value={typeof value === 'string' ? value : ''}
	oninput={(e) => onChange((e.target as HTMLTextAreaElement).value)}
	class="flex-1"
	aria-label={ariaLabel}
/>
