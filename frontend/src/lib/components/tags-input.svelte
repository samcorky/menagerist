<script lang="ts">
	import { X } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { normaliseTags } from '$lib/tags';

	let { tags = $bindable([]) }: { tags?: string[] } = $props();

	const inputId = $props.id();
	let draft = $state('');

	function commit() {
		if (!draft.trim()) {
			draft = '';
			return;
		}
		tags = normaliseTags([...tags, draft]);
		draft = '';
	}

	function removeTag(tag: string) {
		tags = tags.filter((t) => t !== tag);
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ',') {
			e.preventDefault();
			commit();
		} else if (e.key === 'Backspace' && draft === '' && tags.length > 0) {
			tags = tags.slice(0, -1);
		}
	}
</script>

<div class="space-y-2">
	<Label for={inputId}>Tags</Label>
	{#if tags.length > 0}
		<ul class="flex flex-wrap gap-1.5">
			{#each tags as tag (tag)}
				<li>
					<Badge variant="secondary" class="pr-1">
						<span class="max-w-40 truncate" title={tag}>{tag}</span>
						<button
							type="button"
							onclick={() => removeTag(tag)}
							aria-label="Remove tag {tag}"
							class="rounded-full p-0.5 hover:bg-foreground/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
						>
							<X class="size-3" />
						</button>
					</Badge>
				</li>
			{/each}
		</ul>
	{/if}
	<Input
		id={inputId}
		bind:value={draft}
		placeholder="Add a tag"
		autocomplete="off"
		onkeydown={handleKeydown}
		onblur={commit}
	/>
</div>
