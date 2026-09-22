<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { quantityText } from './format';

	let { value, prop: _prop }: { value: unknown; prop: JsonSchemaProperty } = $props();
</script>

<span>{quantityText(value) || '—'}</span>
