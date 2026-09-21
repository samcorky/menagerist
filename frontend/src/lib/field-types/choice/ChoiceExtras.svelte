<script lang="ts">
	import { Plus, X } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { getContext } from 'svelte';
	import { countEdgeTypeAttributeUsage, countNodeTypeAttributeUsage } from '$lib/api/client';
	import { optionRemovalWarning } from '$lib/field-usage';
	import { SCHEMA_TYPE_CONTEXT, type SchemaTypeContext } from '$lib/schema-type-context';
	import type { EditorField } from '$lib/schema-types';

	let {
		field,
		onChange
	}: {
		field: EditorField;
		onChange: (f: EditorField) => void;
	} = $props();

	const ctx = getContext<SchemaTypeContext | undefined>(SCHEMA_TYPE_CONTEXT);

	let draft = $state('');
	let removalWarning = $state<string | null>(null);
	let removalRequest = 0;

	function addOption() {
		const trimmed = draft.trim();
		if (!trimmed || field.options.includes(trimmed)) {
			draft = '';
			return;
		}
		removalRequest++;
		removalWarning = null;
		onChange({ ...field, options: [...field.options, trimmed] });
		draft = '';
	}

	async function removeOption(opt: string) {
		const request = ++removalRequest;
		removalWarning = null;
		onChange({ ...field, options: field.options.filter((o) => o !== opt) });
		const typeId = ctx?.typeId;
		if (!ctx || !typeId || field.keyPending) return;
		const kind = ctx.kind;
		try {
			const result =
				kind === 'node'
					? await countNodeTypeAttributeUsage({
							path: { node_type_id: typeId, key: field.key },
							query: { value: opt }
						})
					: await countEdgeTypeAttributeUsage({
							path: { edge_type_id: typeId, key: field.key },
							query: { value: opt }
						});
			const count = result.data?.count ?? 0;
			if (request === removalRequest && count > 0) {
				removalWarning = optionRemovalWarning(opt, count, kind);
			}
		} catch {
			// Usage is advisory; ignore failures.
		}
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
	{#if removalWarning}
		<p class="text-xs text-muted-foreground" role="status">{removalWarning}</p>
	{/if}
</div>
