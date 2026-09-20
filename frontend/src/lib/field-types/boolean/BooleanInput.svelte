<script lang="ts">
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

<label class="flex items-center gap-2">
	<input
		type="checkbox"
		checked={value === true || value === 'true'}
		onchange={(e) => onChange((e.target as HTMLInputElement).checked ? 'true' : 'false')}
		class="h-4 w-4 rounded border-input accent-primary"
		aria-label={ariaLabel}
	/>
	<span class="sr-only">{ariaLabel}</span>
</label>
