<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import { resolve } from '$app/paths';
	import { Download, Tag, Pencil, Plus, Trash2 } from '@lucide/svelte';
	import ListRowSkeleton from '$lib/components/list-row-skeleton.svelte';
	import ListFoot from '$lib/components/list-foot.svelte';
	import { untrack } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';
	import {
		listNodes,
		listNodeTypes,
		createNodeType,
		updateNodeType,
		deleteNodeType,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { downloadBundle, exportTypeBundle, presetFilename } from '$lib/preset-packs';
	import { slugify } from '$lib/utils.js';
	import { loadExampleIds } from '$lib/examples';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Checkbox } from '$lib/components/ui/checkbox/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import { auth } from '$lib/auth.svelte.js';
	import BackButton from '$lib/components/back-button.svelte';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import LoadFailed from '$lib/components/load-failed.svelte';
	import { offlineController } from '$lib/offline.svelte.js';
	import IconButton from '$lib/components/icon-button.svelte';
	import TypeAppearanceFields from '$lib/components/type-appearance-fields.svelte';
	import TypeEditorDialog from '$lib/components/type-editor-dialog.svelte';
	import TypeIcon from '$lib/components/type-icon.svelte';
	import SchemaEditor from '$lib/components/schema-editor.svelte';
	import type { AttributesSchema } from '$lib/schema-types';

	const PAGE_SIZE = 50;

	let categories = $state<NodeTypeResponse[]>([]);
	let loading = $state(false);
	let exampleTypeIds = $state<ReadonlySet<string>>(new Set());
	let hasMore = $state(true);
	let loadFailed = $state(false);
	// A later page that would not load: the list says so and offers Try again (#588).
	let pageFailed = $state(false);

	// One editor serves both creating (editingId null) and editing.
	let editorOpen = $state(false);
	let editingId = $state<string | null>(null);
	let label = $state('');
	let description = $state('');
	let schema = $state<AttributesSchema | null>(null);
	let icon = $state<string | null>(null);
	let colour = $state<string | null>(null);
	let saving = $state(false);
	let query = $state('');

	let confirmTarget = $state<NodeTypeResponse | null>(null);
	let deletingId = $state<string | null>(null);
	let exportingId = $state<string | null>(null);
	const selectedIds = new SvelteSet<string>();
	// Read from the list so a type that has gone leaves the selection.
	const selected = $derived(categories.filter((c) => selectedIds.has(c.id)));

	async function fetchPage(after?: string) {
		loading = true;
		if (!after) loadFailed = false;
		pageFailed = false;
		const result = await listNodeTypes({ query: { after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			// A later page keeps `hasMore`, so Try again in the list's foot can resume it.
			if (after) pageFailed = true;
			else {
				loadFailed = true;
				hasMore = false;
			}
		} else {
			categories = after ? [...categories, ...result.data] : result.data;
			hasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		loading = false;
	}

	/** Save the types, with the lists they use, as one file someone else can import. */
	async function exportTypes(types: NodeTypeResponse[], filename: string) {
		if (exportingId) return;
		exportingId = types[0].id;
		try {
			downloadBundle(await exportTypeBundle(types.map((t) => t.id)), filename);
		} catch (error) {
			const description = error instanceof Error ? error.message : errorMessage(error);
			toast.error("Couldn't export", { description });
		} finally {
			exportingId = null;
		}
	}

	const handleExport = (cat: NodeTypeResponse) => exportTypes([cat], presetFilename(cat.label));

	function setSelected(id: string, on: boolean) {
		if (on) selectedIds.add(id);
		else selectedIds.delete(id);
	}

	async function exportSelected() {
		if (selected.length === 0) return;
		await exportTypes(selected, presetFilename('Item types'));
		selectedIds.clear();
	}

	function loadMore() {
		if (!hasMore || loading) return;
		void fetchPage(categories.at(-1)?.id);
	}

	function openCreate() {
		editingId = null;
		label = '';
		description = '';
		schema = null;
		icon = null;
		colour = null;
		editorOpen = true;
	}

	function openEdit(cat: NodeTypeResponse) {
		editingId = cat.id;
		label = cat.label;
		description = cat.description ?? '';
		schema = (cat.attributes_schema as AttributesSchema | null) ?? null;
		icon = cat.icon ?? null;
		colour = cat.colour ?? null;
		editorOpen = true;
	}

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		saving = true;
		if (editingId) {
			const id = editingId;
			const result = await updateNodeType({
				path: { node_type_id: id },
				// null removes an icon or colour; leaving the field out would keep it.
				body: {
					label,
					description: description || null,
					attributes_schema: schema,
					icon,
					colour
				}
			});
			if (result.error || !result.data) {
				toast.error("Couldn't save changes", { description: errorMessage(result.error) });
			} else {
				categories = categories.map((c) => (c.id === id ? result.data! : c));
				editorOpen = false;
				toast.success('Item type updated');
			}
		} else {
			const result = await createNodeType({
				body: {
					slug: slugify(label),
					label,
					description: description || undefined,
					attributes_schema: schema,
					icon: icon ?? undefined,
					colour: colour ?? undefined
				}
			});
			if (result.error || !result.data) {
				toast.error("Couldn't create item type", { description: errorMessage(result.error) });
			} else {
				categories = [result.data, ...categories];
				editorOpen = false;
				toast.success('Item type created');
			}
		}
		saving = false;
	}

	const fieldCount = (cat: NodeTypeResponse) =>
		Object.keys((cat.attributes_schema as AttributesSchema | null)?.properties ?? {}).length;

	// Searching only helps once the list is long enough to scan.
	const SEARCH_FROM = 8;
	const shown = $derived(
		query.trim() === ''
			? categories
			: categories.filter((c) =>
					`${c.label} ${c.slug}`.toLowerCase().includes(query.trim().toLowerCase())
				)
	);

	async function handleDelete(cat: NodeTypeResponse) {
		const inUse = await listNodes({ query: { type: cat.slug, limit: 1 } });
		const hasItems = (inUse.data?.length ?? 0) > 0;

		if (hasItems) {
			// Destructive - items will lose their item type. Require explicit confirmation.
			confirmTarget = cat;
			return;
		}

		// No items - optimistic removal with undo window
		categories = categories.filter((c) => c.id !== cat.id);

		let undone = false;
		const timerId = setTimeout(async () => {
			if (undone) return;
			const result = await deleteNodeType({ path: { node_type_id: cat.id } });
			if (result.error) {
				categories = [cat, ...categories];
				toast.error("Couldn't delete item type", { description: errorMessage(result.error) });
			}
		}, 5000);

		toast('Item type deleted', {
			action: {
				label: 'Undo',
				onClick: () => {
					undone = true;
					clearTimeout(timerId);
					categories = [cat, ...categories];
				}
			},
			duration: 5000
		});
	}

	async function confirmDelete() {
		const cat = confirmTarget;
		if (!cat) return;
		deletingId = cat.id;
		const result = await deleteNodeType({ path: { node_type_id: cat.id } });
		if (result.error) {
			toast.error("Couldn't delete item type", { description: errorMessage(result.error) });
		} else {
			categories = categories.filter((c) => c.id !== cat.id);
			toast.success('Item type deleted');
		}
		deletingId = null;
		confirmTarget = null;
	}

	$effect(() => {
		void fetchPage();
		void loadExampleIds().then((ids) => (exampleTypeIds = ids.itemTypes));
	});

	// Coming back online, or Retry in the banner, reloads a list that had failed.
	$effect(() => {
		void offlineController.retryCount;
		untrack(() => {
			if (loadFailed) void fetchPage();
		});
	});
</script>

<svelte:head>
	<title>Item types - Menagerist</title>
</svelte:head>

<Page width="reading">
	<BackButton peer fallback={resolve('/settings')} />

	<div class="flex items-start justify-between gap-4">
		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Item types</h1>
			<p class="mt-1 text-muted-foreground">
				Organise your items with types like "Film", "Person", or "Event".
			</p>
		</div>
		<IconButton label="New item type" variant="default" onclick={openCreate}>
			<Plus />
		</IconButton>
	</div>

	{#if categories.length > SEARCH_FROM}
		<Input type="search" bind:value={query} placeholder="Search item types…" class="sm:max-w-sm" />
	{/if}

	{#if loading && categories.length === 0}
		<ListRowSkeleton count={3} tile />
	{:else if loadFailed}
		<LoadFailed what="your item types" onretry={() => void fetchPage()} />
	{:else}
		{#if selected.length > 0}
			<div
				class="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card px-3 py-2"
			>
				<p class="text-sm text-muted-foreground">
					{selected.length === 1 ? '1 item type' : `${selected.length} item types`} selected. The saved
					fields they use come with them.
				</p>
				<div class="flex gap-2">
					<Button
						variant="outline"
						class="pointer-coarse:h-11"
						disabled={exportingId !== null}
						onclick={() => selectedIds.clear()}
					>
						Clear
					</Button>
					<Button
						class="pointer-coarse:h-11"
						disabled={exportingId !== null}
						onclick={exportSelected}
					>
						<Download data-icon="inline-start" />
						Export {selected.length === 1 ? 'item type' : `${selected.length} item types`}
					</Button>
				</div>
			</div>
		{/if}
		{#if shown.length > 0}
			<ul class="divide-y rounded-xl border bg-card">
				{#each shown as cat (cat.id)}
					<li class="flex items-center gap-3 px-3 py-2">
						<Checkbox
							aria-label="Select {cat.label}"
							checked={selectedIds.has(cat.id)}
							onCheckedChange={(on) => setSelected(cat.id, on)}
						/>
						<TypeIcon
							icon={cat.icon}
							colour={cat.colour}
							boxed
							class="size-8 rounded-lg text-base"
						/>
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-2">
								<span class="truncate font-medium">{cat.label}</span>
								{#if exampleTypeIds.has(cat.id)}
									<Badge variant="outline" class="shrink-0 text-muted-foreground">Example</Badge>
								{/if}
								<span class="min-w-0 truncate font-mono text-xs text-muted-foreground"
									>{cat.slug}</span
								>
							</div>
							{#if cat.description}
								<p class="truncate text-sm text-muted-foreground">{cat.description}</p>
							{/if}
						</div>
						<span class="hidden shrink-0 text-xs text-muted-foreground sm:inline">
							{fieldCount(cat) === 1 ? '1 field' : `${fieldCount(cat)} fields`}
						</span>
						<IconButton
							labelOnTouch={false}
							label="Export item type"
							disabled={exportingId !== null}
							onclick={() => handleExport(cat)}
						>
							<Download />
						</IconButton>
						<IconButton labelOnTouch={false} label="Edit item type" onclick={() => openEdit(cat)}>
							<Pencil />
						</IconButton>
						{#if auth.can('graph:node_type:delete')}
							<IconButton
								labelOnTouch={false}
								label="Delete item type"
								disabled={deletingId === cat.id}
								onclick={() => handleDelete(cat)}
							>
								<Trash2 />
							</IconButton>
						{/if}
					</li>
				{/each}
			</ul>
		{:else if query.trim() !== ''}
			<p class="py-8 text-center text-sm text-muted-foreground">
				No item types match "{query.trim()}".
			</p>
		{/if}

		{#if categories.length === 0 && !loading}
			<div class="flex flex-col items-center gap-3 py-12 text-center">
				<Tag class="size-10 text-muted-foreground/50" />
				<div>
					<p class="font-medium">No item types yet</p>
					<p class="text-sm text-muted-foreground">Create one to start organising your items.</p>
				</div>
			</div>
		{/if}
	{/if}

	<ListFoot
		{loading}
		{hasMore}
		failed={pageFailed}
		rows={categories.length}
		noun="item type"
		onload={loadMore}
		onretry={() => void fetchPage(categories.at(-1)?.id)}
	/>
</Page>

<TypeEditorDialog
	open={editorOpen}
	title={editingId ? 'Edit item type' : 'New item type'}
	submitLabel={editingId ? 'Save' : 'Add item type'}
	busyLabel={editingId ? 'Saving…' : 'Adding…'}
	busy={saving}
	value={{ label, description, schema, icon, colour }}
	onSubmit={handleSubmit}
	onClose={() => (editorOpen = false)}
>
	<div class="space-y-1.5">
		<Label for="cat-label">Name</Label>
		<Input
			id="cat-label"
			bind:value={label}
			type="text"
			placeholder="e.g. Film, Person, Place"
			required
		/>
	</div>
	<div class="space-y-1.5">
		<Label for="cat-description">Description</Label>
		<Textarea id="cat-description" bind:value={description} placeholder="Optional description" />
	</div>
	<TypeAppearanceFields bind:icon bind:colour />
	<SchemaEditor
		bind:schema
		typeId={editingId ?? undefined}
		typeKind={editingId ? 'node' : undefined}
		highlights
	/>
</TypeEditorDialog>

<ConfirmDialog
	open={confirmTarget !== null}
	title="Delete item type?"
	description={confirmTarget
		? `Items using "${confirmTarget.label}" will lose this item type.`
		: undefined}
	busy={deletingId !== null}
	busyLabel="Deleting…"
	confirmLabel="Delete anyway"
	onOpenChange={(v) => {
		if (!v) confirmTarget = null;
	}}
	onConfirm={confirmDelete}
/>
