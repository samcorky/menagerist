<script lang="ts">
	import { Badge } from '$lib/components/ui/badge/index.js';

	let { value }: { value: unknown } = $props();

	let text = $derived(value == null ? '' : String(value));
</script>

{#if text !== ''}
	<Badge variant="secondary" class="max-w-32 truncate" title={text}>{text}</Badge>
{/if}
