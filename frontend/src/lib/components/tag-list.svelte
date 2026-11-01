<script lang="ts">
	import { Badge } from '$lib/components/ui/badge/index.js';

	let {
		tags,
		max,
		compact = false
	}: {
		tags: string[];
		/** Cap how many tags render, with a "+N" badge for the rest. Unset shows all. */
		max?: number;
		/** Smaller chips, for tight spaces like a grid card. */
		compact?: boolean;
	} = $props();

	let shown = $derived(max !== undefined ? tags.slice(0, max) : tags);
	let overflow = $derived(max !== undefined ? Math.max(0, tags.length - max) : 0);
	let chipClass = $derived(compact ? 'h-4 px-1.5 text-[10px]' : undefined);
</script>

{#if tags.length > 0}
	<ul class="flex flex-wrap gap-1" aria-label="Tags">
		{#each shown as tag (tag)}
			<li>
				<Badge variant="secondary" class={chipClass}>
					<span class="max-w-40 truncate" title={tag}>{tag}</span>
				</Badge>
			</li>
		{/each}
		{#if overflow > 0}
			<li>
				<Badge variant="outline" class={chipClass}>+{overflow}</Badge>
			</li>
		{/if}
	</ul>
{/if}
