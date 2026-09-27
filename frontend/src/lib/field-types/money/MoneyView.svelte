<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { moneyText } from './format';

	let { value, prop: _prop }: { value: unknown; prop: JsonSchemaProperty } = $props();
</script>

<span>{moneyText(value) || '-'}</span>
