<script lang="ts">
	import { untrack } from 'svelte';
	import { SvelteMap, SvelteSet } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';
	import { addItemsToCollection, listNodes, type NodeResponse } from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import { addItemsErrorMessage, describeAddResult } from '$lib/collections';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';

	const PAGE_SIZE = 50;
	const MEMBER_PAGE_SIZE = 500;
	const MAX_MEMBER_IDS = 20_000;
	const MAX_SELECTION = 500;

	let {
		open,
		collectionId,
		typeLabels = {},
		onOpenChange,
		onAdded
	}: {
		open: boolean;
		collectionId: string;
		/** Item type slug to display label. */
		typeLabels?: Record<string, string>;
		onOpenChange: (open: boolean) => void;
		onAdded: () => void;
	} = $props();

	let searchInput = $state('');
	let q = $state('');
	let results = $state<NodeResponse[]>([]);
	let loading = $state(false);
	let hasMore = $state(false);
	let loadFailed = $state(false);
	let memberIds = $state<ReadonlySet<string>>(new Set());
	const selected = new SvelteMap<string, string>();
	let adding = $state(false);
	let addError = $state<string | null>(null);
	let fetchSeq = 0;
	let memberSeq = 0;
	let membersPartial = $state(false);

	const selectedCount = $derived(selected.size);
	const atLimit = $derived(selectedCount >= MAX_SELECTION);

	$effect(() => {
		if (!open) return;
		const id = collectionId;
		untrack(() => {
			searchInput = '';
			q = '';
			results = [];
			selected.clear();
			addError = null;
			memberIds = new Set();
			membersPartial = false;
		});
		void loadMemberIds(id);
	});

	$effect(() => {
		const value = searchInput;
		const timer = setTimeout(() => {
			if (value === q) return;
			results = [];
			hasMore = false;
			q = value;
		}, 300);
		return () => clearTimeout(timer);
	});

	$effect(() => {
		if (!open) return;
		void fetchPage(q);
	});

	// Best effort: the server skips items already there either way.
	async function loadMemberIds(id: string) {
		const seq = ++memberSeq;
		const ids = new SvelteSet<string>();
		let after: string | undefined;
		let complete = false;
		while (ids.size < MAX_MEMBER_IDS) {
			const result = await listNodes({
				query: { after, limit: MEMBER_PAGE_SIZE, collection: id }
			});
			if (seq !== memberSeq) return;
			if (result.error || !result.data) break;
			for (const item of result.data) ids.add(item.id);
			if (!/rel="next"/.test(result.response?.headers.get('link') ?? '')) {
				complete = true;
				break;
			}
			after = result.data.at(-1)?.id;
		}
		memberIds = ids;
		membersPartial = !complete;
	}

	async function fetchPage(search: string, after?: string) {
		const seq = ++fetchSeq;
		loading = true;
		if (!after) loadFailed = false;
		const result = await listNodes({
			query: { after, limit: PAGE_SIZE, q: search || undefined }
		});
		if (seq !== fetchSeq) return;
		if (result.error || !result.data) {
			if (after) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
			} else {
				loadFailed = true;
			}
			hasMore = false;
		} else {
			results = after ? [...results, ...result.data] : result.data;
			hasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		loading = false;
	}

	function toggle(item: NodeResponse, checked: boolean) {
		if (checked) {
			if (selected.size < MAX_SELECTION) selected.set(item.id, item.name);
		} else {
			selected.delete(item.id);
		}
	}

	async function handleAdd() {
		if (selectedCount === 0 || adding) return;
		adding = true;
		addError = null;
		const ids = [...selected.keys()];
		const result = await addItemsToCollection({
			path: { collection_id: collectionId },
			body: { item_ids: ids }
		});
		adding = false;
		if (result.error || !result.data) {
			const status = result.response?.status;
			if (status === undefined) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
			} else {
				addError = addItemsErrorMessage(status);
			}
			return;
		}
		toast.success(describeAddResult(result.data.added, ids.length));
		onAdded();
		onOpenChange(false);
	}

	function handleOpenChange(value: boolean) {
		if (!value && adding) return;
		onOpenChange(value);
	}
</script>

<ResponsiveDialog.Root {open} onOpenChange={handleOpenChange}>
	<ResponsiveDialog.Content title="Add items" size="lg">
		<div class="mt-4 space-y-3">
			<input
				bind:value={searchInput}
				type="search"
				placeholder="Search your items…"
				aria-label="Search your items"
				autocomplete="off"
				class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none"
			/>

			<div class="max-h-72 overflow-y-auto rounded-md border" aria-busy={loading}>
				{#if loadFailed}
					<div class="flex flex-col items-start gap-2 p-4">
						<p class="text-sm text-muted-foreground">Couldn't load your items.</p>
						<Button variant="outline" size="sm" onclick={() => void fetchPage(q)}>Try again</Button>
					</div>
				{:else if results.length === 0 && !loading}
					<p class="p-4 text-sm text-muted-foreground">
						{q ? `Nothing matched "${q}".` : 'You have no items yet.'}
					</p>
				{:else}
					<ul class="divide-y">
						{#each results as item (item.id)}
							{@const already = memberIds.has(item.id)}
							{@const isChecked = selected.has(item.id)}
							<li>
								<label
									class="flex items-center gap-3 px-3 py-2.5 text-sm {already
										? 'cursor-not-allowed opacity-60'
										: 'cursor-pointer hover:bg-accent'}"
								>
									<input
										type="checkbox"
										class="size-4 shrink-0 accent-primary"
										checked={already || isChecked}
										disabled={already || (atLimit && !isChecked)}
										onchange={(e) => toggle(item, e.currentTarget.checked)}
										aria-label={already ? `${item.name} (already added)` : `Select ${item.name}`}
									/>
									<span class="min-w-0 flex-1 truncate">{item.name}</span>
									<span class="shrink-0 text-xs text-muted-foreground">
										{already
											? 'Already added'
											: ((item.type && typeLabels[item.type]) ?? item.type ?? '')}
									</span>
								</label>
							</li>
						{/each}
					</ul>
					{#if hasMore}
						<div class="flex justify-center border-t p-2">
							<Button
								variant="ghost"
								size="sm"
								disabled={loading}
								onclick={() => void fetchPage(q, results.at(-1)?.id)}
							>
								{loading ? 'Loading…' : 'Load more'}
							</Button>
						</div>
					{/if}
				{/if}
			</div>

			<p class="text-sm text-muted-foreground" aria-live="polite">
				{selectedCount === 0
					? 'Tick the items to add.'
					: `${selectedCount} ${selectedCount === 1 ? 'item' : 'items'} selected`}
				{#if atLimit}
					- you can add up to {MAX_SELECTION} items at a time.
				{/if}
			</p>

			{#if membersPartial}
				<p class="text-xs text-muted-foreground">
					Some items may already be in this collection. They will be skipped.
				</p>
			{/if}

			{#if addError}
				<p role="alert" class="text-sm text-destructive">{addError}</p>
			{/if}

			<div class="flex justify-end gap-2">
				<Button type="button" variant="outline" onclick={() => handleOpenChange(false)}>
					Cancel
				</Button>
				<Button type="button" disabled={selectedCount === 0 || adding} onclick={handleAdd}>
					{#if adding}
						Adding…
					{:else}
						Add {selectedCount === 0
							? 'items'
							: `${selectedCount} ${selectedCount === 1 ? 'item' : 'items'}`}
					{/if}
				</Button>
			</div>
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
