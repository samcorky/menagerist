<script lang="ts">
	import { Plus, X } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import type { EditorField } from '$lib/schema-types';

	let {
		field,
		onChange
	}: {
		field: EditorField;
		onChange: (f: EditorField) => void;
	} = $props();

	let draft = $state('');

	function addOption() {
		const trimmed = draft.trim();
		if (!trimmed || field.options.includes(trimmed)) {
			draft = '';
			return;
		}
		onChange({ ...field, options: [...field.options, trimmed] });
		draft = '';
	}

	function removeOption(opt: string) {
		onChange({ ...field, options: field.options.filter((o) => o !== opt) });
	}
</script>

<div class="mt-1.5 ml-4 space-y-1.5 border-l border-input pl-3">
	<p class="text-xs text-muted-foreground">Options</p>
	{#if field.options.length > 0}
		<ul class="flex flex-wrap gap-1">
			{#each field.options as opt (opt)}
				<li>
					<Badge variant="secondary" class="pr-1">
						<span class="max-w-32 truncate" title={opt}>{opt}</span>
						<button
							type="button"
							onclick={() => removeOption(opt)}
							aria-label="Remove option {opt}"
							class="ml-1 rounded-full p-0.5 hover:bg-foreground/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
						>
							<X class="size-3" />
						</button>
					</Badge>
				</li>
			{/each}
		</ul>
	{/if}
	<div class="flex gap-1.5">
		<Input
			bind:value={draft}
			placeholder="Add option…"
			class="h-7 w-36 text-xs"
			onkeydown={(e) => {
				if (e.key === 'Enter') {
					e.preventDefault();
					addOption();
				}
			}}
		/>
		<Button type="button" variant="ghost" size="sm" class="h-7 px-2" onclick={addOption}>
			<Plus class="size-3" />
		</Button>
	</div>
</div>
