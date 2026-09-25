<script lang="ts">
	import { ChevronDown, ChevronUp, Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let {
		value,
		onChange,
		ariaLabel,
		prop: _prop
	}: {
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	} = $props();

	let items = $derived(Array.isArray(value) ? (value as { text: string; done: boolean }[]) : []);

	function setText(i: number, text: string) {
		onChange(items.map((it, ii) => (ii === i ? { ...it, text } : it)));
	}

	function setDone(i: number, done: boolean) {
		onChange(items.map((it, ii) => (ii === i ? { ...it, done } : it)));
	}

	function moveItem(i: number, direction: -1 | 1) {
		const j = i + direction;
		const next = [...items];
		[next[i], next[j]] = [next[j], next[i]];
		onChange(next);
	}

	function removeItem(i: number) {
		onChange(items.filter((_, ii) => ii !== i));
	}

	function addItem() {
		onChange([...items, { text: '', done: false }]);
	}
</script>

<div class="flex-1 space-y-2">
	{#if items.length === 0}
		<p class="text-xs text-muted-foreground">No items yet</p>
	{:else}
		<ul class="space-y-1">
			{#each items as item, i (i)}
				<li class="flex items-center gap-2">
					<input
						type="checkbox"
						checked={item.done}
						onchange={(e) => setDone(i, (e.target as HTMLInputElement).checked)}
						class="h-4 w-4 shrink-0 rounded border-input accent-primary"
						aria-label="{ariaLabel} item {i + 1} done"
					/>
					<Input
						value={item.text}
						oninput={(e) => setText(i, (e.target as HTMLInputElement).value)}
						aria-label="{ariaLabel} item {i + 1}"
						class="flex-1 {item.done ? 'text-muted-foreground line-through' : ''}"
					/>
					<Button
						type="button"
						variant="ghost"
						size="icon"
						disabled={i === 0}
						onclick={() => moveItem(i, -1)}
						aria-label="Move item {i + 1} earlier"
					>
						<ChevronUp class="size-4" />
					</Button>
					<Button
						type="button"
						variant="ghost"
						size="icon"
						disabled={i === items.length - 1}
						onclick={() => moveItem(i, 1)}
						aria-label="Move item {i + 1} later"
					>
						<ChevronDown class="size-4" />
					</Button>
					<Button
						type="button"
						variant="ghost"
						size="icon"
						onclick={() => removeItem(i)}
						aria-label="Remove item {i + 1}"
					>
						<X class="size-4" />
					</Button>
				</li>
			{/each}
		</ul>
	{/if}
	<Button type="button" variant="outline" size="sm" onclick={addItem}>
		<Plus class="size-4" />
		Add item
	</Button>
</div>
