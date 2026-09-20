<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let {
		value,
		prop: _prop
	}: {
		value: unknown;
		prop: JsonSchemaProperty;
	} = $props();
</script>

<input
	type="checkbox"
	checked={value === true || value === 'true'}
	class="pointer-events-none h-4 w-4 cursor-default rounded border-input accent-primary"
/>
