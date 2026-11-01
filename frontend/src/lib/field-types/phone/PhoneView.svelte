<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let { value, prop: _prop }: { value: unknown; prop: JsonSchemaProperty } = $props();

	let number = $derived(typeof value === 'string' && value !== '' ? value : null);
</script>

{#if number}
	<a href="tel:{number}" class="text-primary underline">{number}</a>
{:else}
	<span>-</span>
{/if}
