<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { addItemsToCollection, type CollectionResponse } from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { itemCount, unknownItemIds } from '$lib/bulk-actions';
	import { describeAddResult, fetchAllCollections } from '$lib/collections';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';

	let {
		open,
		ids,
		onOpenChange,
		ondone,
		onmissing
	}: {
		open: boolean;
		ids: string[];
		onOpenChange: (open: boolean) => void;
		ondone: () => void;
		onmissing: (ids: string[]) => void;
	} = $props();

	let collections = $state<CollectionResponse[] | null>(null);
	let loadFailed = $state(false);
	let chosen = $state('');
	let sending = $state(false);
	let error = $state<string | null>(null);

	// Items are put on a collection by hand; a smart collection fills itself.
	const manual = $derived((collections ?? []).filter((c) => c.kind === 'manual'));

	$effect(() => {
		if (!open) return;
		chosen = '';
		error = null;
		loadFailed = false;
		void fetchAllCollections().then((all) => {
			collections = all;
			loadFailed = all === null;
		});
	});

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		if (sending || !chosen) return;
		sending = true;
		error = null;
		const result = await addItemsToCollection({
			path: { collection_id: chosen },
			body: { item_ids: ids }
		});
		sending = false;
		if (result.error || !result.data) {
			if (!result.response) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
				return;
			}
			const detail = errorMessage(result.error);
			error = detail;
			const missing = unknownItemIds(detail);
			if (missing.length > 0) onmissing(missing);
			return;
		}
		toast.success(describeAddResult(result.data.added, ids.length));
		ondone();
		onOpenChange(false);
	}
</script>

<ResponsiveDialog.Root {open} onOpenChange={(value) => !sending && onOpenChange(value)}>
	<ResponsiveDialog.Content title="Add {itemCount(ids.length)} to a collection">
		<form class="mt-4 space-y-4" onsubmit={submit}>
			{#if loadFailed}
				<p class="text-sm text-muted-foreground">Couldn't load your collections.</p>
			{:else if collections !== null && manual.length === 0}
				<p class="text-sm text-muted-foreground">
					You have no collections to add to yet. Create one from the Collections page.
				</p>
			{:else}
				<div class="space-y-1.5">
					<Label for="bulk-collection">Collection</Label>
					<NativeSelect.Root
						id="bulk-collection"
						bind:value={chosen}
						disabled={collections === null}
					>
						<NativeSelect.Option value="">Choose a collection</NativeSelect.Option>
						{#each manual as collection (collection.id)}
							<NativeSelect.Option value={collection.id}>{collection.name}</NativeSelect.Option>
						{/each}
					</NativeSelect.Root>
				</div>
			{/if}
			{#if error}
				<p role="alert" class="text-sm text-destructive">{error}</p>
			{/if}
			<div class="flex justify-end gap-2">
				<Button type="button" variant="outline" onclick={() => onOpenChange(false)}>Cancel</Button>
				<Button type="submit" disabled={sending || !chosen}>
					{sending ? 'Adding…' : 'Add'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
