<script lang="ts">
	import { Badge } from '$lib/components/ui/badge/index.js';
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let { value, prop }: { value: unknown; prop: JsonSchemaProperty } = $props();
</script>

{#if (value === true || value === 'true') && prop.title}
	<Badge variant="outline" class="max-w-32 truncate" title={prop.title}>{prop.title}</Badge>
{/if}
