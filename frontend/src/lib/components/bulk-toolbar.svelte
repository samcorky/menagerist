<script lang="ts">
	import type { Snippet } from 'svelte';
	import { FolderPlus, Link, Tag, Trash2 } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import type { PendingDeletes } from '$lib/pending-deletes.svelte';
	import { SELECTION_LIMIT, type Selection } from '$lib/selection.svelte';
	import BulkCollectionDialog from './bulk-collection-dialog.svelte';
	import BulkConnectDialog from './bulk-connect-dialog.svelte';
	import BulkTagDialog from './bulk-tag-dialog.svelte';
	import SelectionBar from './selection-bar.svelte';

	let {
		selection,
		pending,
		visibleIds,
		canCollect = true,
		onreload,
		extra
	}: {
		selection: Selection;
		pending: PendingDeletes;
		/** The rows in view, in order: Select all acts on these only. */
		visibleIds: string[];
		/** Whether the person may change collections; without it the collection actions are hidden. */
		canCollect?: boolean;
		/** Reload the page's list after an action changed it. */
		onreload: () => Promise<void> | void;
		/** Page-specific actions, such as taking items off the collection being viewed. */
		extra?: Snippet<[{ disabled: boolean }]>;
	} = $props();

	let dialog = $state<'tag' | 'collection' | 'connect' | null>(null);

	const ids = $derived([...selection.ids]);
	const visibleSelected = $derived(visibleIds.filter((id) => selection.has(id)).length);

	function toggleVisible() {
		if (visibleSelected === visibleIds.length) selection.deselectAll(visibleIds);
		else selection.selectAll(visibleIds);
	}

	function drop(missing: string[]) {
		selection.drop(missing);
		void onreload();
	}

	function remove() {
		const doomed = ids;
		selection.clear();
		pending.start(doomed, {
			onsent: onreload,
			onmissing: drop,
			// Undo or a refusal puts the picks back, unless the person has left selection mode since.
			onrestore: () => {
				if (selection.active) selection.selectAll(doomed);
			}
		});
	}

	function done() {
		selection.clear();
		void onreload();
	}
</script>

<SelectionBar
	count={selection.count}
	hidden={selection.hiddenCount(visibleIds)}
	limit={SELECTION_LIMIT}
	{visibleSelected}
	visibleTotal={visibleIds.length}
	ontogglevisible={toggleVisible}
	onclear={() => selection.clear()}
	onexit={() => selection.exit()}
>
	{#snippet actions({ disabled })}
		<Button
			variant="outline"
			size="sm"
			class="pointer-coarse:h-11"
			{disabled}
			onclick={() => (dialog = 'tag')}
		>
			<Tag />
			Tag
		</Button>
		{#if canCollect}
			<Button
				variant="outline"
				size="sm"
				class="pointer-coarse:h-11"
				{disabled}
				onclick={() => (dialog = 'collection')}
			>
				<FolderPlus />
				Add to collection
			</Button>
		{/if}
		<Button
			variant="outline"
			size="sm"
			class="pointer-coarse:h-11"
			{disabled}
			onclick={() => (dialog = 'connect')}
		>
			<Link />
			Connect
		</Button>
		{@render extra?.({ disabled })}
		<Button variant="destructive" size="sm" class="pointer-coarse:h-11" {disabled} onclick={remove}>
			<Trash2 />
			Delete
		</Button>
	{/snippet}
</SelectionBar>

<BulkTagDialog
	open={dialog === 'tag'}
	{ids}
	onOpenChange={(open) => !open && (dialog = null)}
	ondone={done}
	onmissing={drop}
/>
<BulkCollectionDialog
	open={dialog === 'collection'}
	{ids}
	onOpenChange={(open) => !open && (dialog = null)}
	ondone={done}
	onmissing={drop}
/>
<BulkConnectDialog
	open={dialog === 'connect'}
	{ids}
	onOpenChange={(open) => !open && (dialog = null)}
	ondone={done}
	onmissing={drop}
/>
