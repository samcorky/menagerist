<script lang="ts">
	import { resolve } from '$app/paths';
	import { Plus, X } from '@lucide/svelte';
	import { tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		addItemsToCollection,
		createCollection,
		listCollections,
		removeItemFromCollection,
		type CollectionResponse
	} from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import {
		MAX_COLLECTION_NAME_LENGTH,
		addItemsErrorMessage,
		collectionSaveErrorMessage,
		validateCollectionName
	} from '$lib/collections';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';

	const PAGE_SIZE = 50;
	const MAX_PAGES = 10;

	let { itemId }: { itemId: string } = $props();

	let memberOf = $state<CollectionResponse[]>([]);
	let loading = $state(true);
	let loadFailed = $state(false);

	let pickerOpen = $state(false);
	let allCollections = $state<CollectionResponse[]>([]);
	let pickerLoading = $state(false);
	let pickerFailed = $state(false);
	let busyId = $state<string | null>(null);
	let newName = $state('');
	let newTouched = $state(false);
	let creating = $state(false);
	let createError = $state<string | null>(null);
	let trigger: HTMLElement | null = null;

	const memberIds = $derived(new Set(memberOf.map((c) => c.id)));
	const newNameHint = $derived(validateCollectionName(newName));
	const showNewNameHint = $derived(newTouched && newNameHint !== null);

	async function fetchAll(query: { item_id?: string }): Promise<CollectionResponse[] | null> {
		const found: CollectionResponse[] = [];
		let after: string | undefined;
		for (let i = 0; i < MAX_PAGES; i++) {
			const result = await listCollections({ query: { ...query, after, limit: PAGE_SIZE } });
			if (result.error || !result.data) return null;
			found.push(...result.data);
			if (!/rel="next"/.test(result.response?.headers.get('link') ?? '')) break;
			after = result.data.at(-1)?.id;
		}
		return found;
	}

	async function loadMemberOf(id: string) {
		const found = await fetchAll({ item_id: id });
		if (id !== itemId) return;
		if (found) {
			memberOf = found;
			loadFailed = false;
		} else {
			loadFailed = true;
		}
		loading = false;
	}

	$effect(() => {
		const id = itemId;
		loading = true;
		void loadMemberOf(id);
	});

	async function loadPicker() {
		pickerLoading = true;
		pickerFailed = false;
		const found = await fetchAll({});
		if (found) allCollections = found;
		else pickerFailed = true;
		pickerLoading = false;
	}

	function openPicker(event: MouseEvent) {
		trigger = event.currentTarget as HTMLElement;
		newName = '';
		newTouched = false;
		createError = null;
		pickerOpen = true;
		void loadPicker();
	}

	function handlePickerOpenChange(open: boolean) {
		if (!open && (creating || busyId !== null)) return;
		pickerOpen = open;
		if (!open) void tick().then(() => trigger?.focus());
	}

	async function addTo(collection: CollectionResponse) {
		busyId = collection.id;
		const result = await addItemsToCollection({
			path: { collection_id: collection.id },
			body: { item_ids: [itemId] }
		});
		busyId = null;
		if (result.error) {
			toast.error(addItemsErrorMessage(result.response?.status));
			return;
		}
		toast.success(`Added to ${collection.name}`);
		handlePickerOpenChange(false);
		void loadMemberOf(itemId);
	}

	async function handleCreate(event: SubmitEvent) {
		event.preventDefault();
		newTouched = true;
		if (newNameHint !== null || creating) return;
		creating = true;
		createError = null;
		const created = await createCollection({ body: { name: newName.trim() } });
		if (created.error || !created.data) {
			creating = false;
			const status = created.response?.status;
			if (status === undefined) {
				const { title, description } = networkAwareError(created);
				toast.error(title, { description });
			} else {
				createError = collectionSaveErrorMessage(status);
			}
			return;
		}
		const added = await addItemsToCollection({
			path: { collection_id: created.data.id },
			body: { item_ids: [itemId] }
		});
		creating = false;
		if (added.error) {
			toast.error(`Created ${created.data.name}, but couldn't add this item to it. Try again.`);
		} else {
			toast.success(`Added to ${created.data.name}`);
		}
		handlePickerOpenChange(false);
		void loadMemberOf(itemId);
	}

	async function removeFrom(collection: CollectionResponse) {
		busyId = collection.id;
		const result = await removeItemFromCollection({
			path: { collection_id: collection.id, item_id: itemId }
		});
		busyId = null;
		if (result.error) {
			const { title, description } = networkAwareError(result);
			toast.error(title, { description });
			return;
		}
		memberOf = memberOf.filter((c) => c.id !== collection.id);
		toast.success(`Removed from ${collection.name}`);
	}
</script>

<Card.Root>
	<Card.Header class="flex flex-row items-center justify-between gap-2">
		<Card.Title class="font-heading">Collections</Card.Title>
		{#if !loading}
			<Button type="button" variant="outline" size="sm" onclick={openPicker}>
				<Plus class="size-4" />
				Add to collection
			</Button>
		{/if}
	</Card.Header>
	<Card.Content>
		{#if loadFailed}
			<div class="flex flex-col items-start gap-2">
				<p class="text-sm text-muted-foreground">Couldn't load this item's collections.</p>
				<Button variant="outline" size="sm" onclick={() => void loadMemberOf(itemId)}>
					Try again
				</Button>
			</div>
		{:else if !loading && memberOf.length === 0}
			<p class="text-sm text-muted-foreground">Not in any collection yet.</p>
		{:else if memberOf.length > 0}
			<ul class="flex flex-wrap gap-2">
				{#each memberOf as collection (collection.id)}
					<li class="flex items-center rounded-full border bg-background text-sm">
						<a
							href={resolve('/collections/[id]', { id: collection.id })}
							class="rounded-l-full py-1 pr-1 pl-3 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
						>
							{collection.name}
						</a>
						<button
							type="button"
							onclick={() => void removeFrom(collection)}
							disabled={busyId === collection.id}
							aria-label="Remove from {collection.name}"
							class="relative rounded-r-full p-1.5 text-muted-foreground transition-colors after:absolute after:-inset-1 after:content-[''] hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:opacity-50"
						>
							<X class="size-3.5" />
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</Card.Content>
</Card.Root>

<ResponsiveDialog.Root open={pickerOpen} onOpenChange={handlePickerOpenChange}>
	<ResponsiveDialog.Content title="Add to collection" size="md">
		<div class="mt-4 space-y-4">
			{#if pickerFailed}
				<div class="flex flex-col items-start gap-2">
					<p class="text-sm text-muted-foreground">Couldn't load your collections.</p>
					<Button variant="outline" size="sm" onclick={() => void loadPicker()}>Try again</Button>
				</div>
			{:else if pickerLoading && allCollections.length === 0}
				<p class="text-sm text-muted-foreground">Loading…</p>
			{:else if allCollections.length > 0}
				<ul class="max-h-60 divide-y overflow-y-auto rounded-md border">
					{#each allCollections as collection (collection.id)}
						{@const added = memberIds.has(collection.id)}
						<li>
							<button
								type="button"
								disabled={added || busyId !== null}
								onclick={() => void addTo(collection)}
								class="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-transparent"
							>
								<span class="min-w-0 truncate">{collection.name}</span>
								{#if added}
									<span class="shrink-0 text-xs text-muted-foreground">Added</span>
								{/if}
							</button>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="text-sm text-muted-foreground">You have no collections yet.</p>
			{/if}

			<form class="space-y-2 border-t pt-4" onsubmit={handleCreate} novalidate>
				<Label for="item-new-collection-name">New collection</Label>
				<div class="flex gap-2">
					<Input
						id="item-new-collection-name"
						bind:value={newName}
						maxlength={MAX_COLLECTION_NAME_LENGTH}
						placeholder="Name"
						autocomplete="off"
						aria-invalid={showNewNameHint}
						aria-describedby={showNewNameHint ? 'item-new-collection-hint' : undefined}
						onblur={() => (newTouched = true)}
					/>
					<Button type="submit" disabled={creating} class="shrink-0">
						{creating ? 'Creating…' : 'Create and add'}
					</Button>
				</div>
				{#if showNewNameHint}
					<p id="item-new-collection-hint" class="text-sm text-destructive">{newNameHint}</p>
				{/if}
				{#if createError}
					<p role="alert" class="text-sm text-destructive">{createError}</p>
				{/if}
			</form>

			<div class="flex justify-end">
				<Button type="button" variant="outline" onclick={() => handlePickerOpenChange(false)}>
					Close
				</Button>
			</div>
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
