<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let { value, prop: _prop }: { value: unknown; prop: JsonSchemaProperty } = $props();

	let items = $derived(
		Array.isArray(value) ? value.map((it) => it as { text: unknown; done: unknown }) : []
	);
</script>

{#if items.length === 0}
	<span class="text-muted-foreground">—</span>
{:else}
	<ul class="space-y-0.5 text-sm">
		{#each items as item, i (i)}
			{@const done = item.done === true}
			<li class="flex items-center gap-2">
				<input
					type="checkbox"
					checked={done}
					class="pointer-events-none h-4 w-4 cursor-default rounded border-input accent-primary"
				/>
				<span class={done ? 'text-muted-foreground line-through' : ''}>{String(item.text)}</span>
			</li>
		{/each}
	</ul>
{/if}
