<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let { value, prop: _prop }: { value: unknown; prop: JsonSchemaProperty } = $props();

	let text = $derived(typeof value === 'string' && value !== '' ? value : null);
	let href = $derived(text && /^https?:\/\//i.test(text) ? text : null);
</script>

{#if href}
	<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- external link, not an app route -->
	<a {href} target="_blank" rel="noopener noreferrer" class="break-all text-primary underline"
		>{href}</a
	>
{:else if text}
	<span class="break-all">{text}</span>
{:else}
	<span>-</span>
{/if}
