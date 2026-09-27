<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let { value, prop: _prop }: { value: unknown; prop: JsonSchemaProperty } = $props();

	let address = $derived(typeof value === 'string' && value !== '' ? value : null);
</script>

{#if address}
	<a href="mailto:{address}" class="break-all text-primary underline">{address}</a>
{:else}
	<span>-</span>
{/if}
