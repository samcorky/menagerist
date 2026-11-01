<script lang="ts">
	import { ChevronDown, ChevronUp, Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import { readPropMeta } from '$lib/schema-meta';
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let {
		value,
		onChange,
		ariaLabel,
		prop
	}: {
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	} = $props();

	let items = $derived(Array.isArray(value) ? (value as string[]) : []);
	let bulleted = $derived(readPropMeta(prop).display === 'bulleted');
	let multiline = $derived(readPropMeta(prop).multiline === true);

	function setItem(i: number, val: string) {
		onChange(items.map((it, ii) => (ii === i ? val : it)));
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
		onChange([...items, '']);
	}
</script>

<div class="flex-1 space-y-2">
	{#if items.length === 0}
		<p class="text-xs text-muted-foreground">No items yet</p>
	{:else}
		<ul class="space-y-1">
			{#each items as item, i (i)}
				<li class="flex gap-2 {multiline ? 'items-start' : 'items-center'}">
					<span class="w-6 shrink-0 text-right text-sm text-muted-foreground">
						{bulleted ? '•' : `${i + 1}.`}
					</span>
					{#if multiline}
						<Textarea
							value={item}
							oninput={(e) => setItem(i, (e.target as HTMLTextAreaElement).value)}
							aria-label="{ariaLabel} item {i + 1}"
							class="flex-1"
						/>
					{:else}
						<Input
							value={item}
							oninput={(e) => setItem(i, (e.target as HTMLInputElement).value)}
							aria-label="{ariaLabel} item {i + 1}"
							class="flex-1"
						/>
					{/if}
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
