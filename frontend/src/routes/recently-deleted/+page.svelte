<script lang="ts">
	import { tick } from 'svelte';
	import { resolve } from '$app/paths';
	import { toast } from 'svelte-sonner';
	import { RotateCcw, Trash2 } from '@lucide/svelte';
	import {
		listDeletedCollections,
		listDeletedNodes,
		purgeCollection,
		purgeNode,
		restoreCollection,
		restoreNode
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { auth } from '$lib/auth.svelte.js';
	import { fetchAllNodeTypes } from '$lib/node-types';
	import {
		NOTHING_DELETED_MESSAGE,
		DELETED_PAGE_SIZE,
		deletedCollectionBadge,
		deletedItemType,
		describeDeleted,
		nextCursor,
		purgeDescription,
		deletedActionError,
		type DeletedTab
	} from '$lib/recently-deleted';
	import { formatDateTime } from '$lib/format-date';
	import { wide } from '$lib/viewport.svelte';
	import BackButton from '$lib/components/back-button.svelte';
	import DataTable from '$lib/components/data-table.svelte';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';
	import * as Table from '$lib/components/ui/table/index.js';

	type Row = {
		id: string;
		name: string;
		deletedAt: string;
		type?: string | null;
		badge?: 'Smart' | 'List';
	};
	type Pane = {
		rows: Row[];
		total: number | null;
		cursor: string | null;
		loading: boolean;
		loadingMore: boolean;
		error: string | null;
	};

	const emptyPane = (): Pane => ({
		rows: [],
		total: null,
		cursor: null,
		loading: true,
		loadingMore: false,
		error: null
	});

	let tab = $state<DeletedTab>('items');
	let panes = $state<Record<DeletedTab, Pane>>({ items: emptyPane(), collections: emptyPane() });
	let typeLabels = $state<Record<string, string>>({});
	let now = $state(new Date());
	let busyId = $state<string | null>(null);
	let actionError = $state<{ id: string; message: string } | null>(null);
	let purgeTarget = $state<{ tab: DeletedTab; row: Row } | null>(null);
	let listEl = $state<HTMLElement>();

	const pane = $derived(panes[tab]);
	const canRestore = $derived(
		tab === 'items' ? auth.can('graph:item:write') : auth.can('collections:collection:write')
	);
	const canPurge = $derived(
		tab === 'items' ? auth.can('graph:item:purge') : auth.can('collections:collection:purge')
	);

	async function fetchPage(which: DeletedTab, after: string | null) {
		const query = { limit: DELETED_PAGE_SIZE, ...(after ? { after } : {}) };
		if (which === 'items') {
			const result = await listDeletedNodes({ query });
			if (result.error || !result.data) return { error: networkAwareError(result).title };
			const rows: Row[] = result.data.map((r) => ({
				id: r.id,
				name: r.name,
				deletedAt: r.deleted_at,
				type: r.type
			}));
			return { rows, ids: result.data, response: result.response };
		}
		const result = await listDeletedCollections({ query });
		if (result.error || !result.data) return { error: networkAwareError(result).title };
		const rows: Row[] = result.data.map((r) => ({
			id: r.id,
			name: r.name,
			deletedAt: r.deleted_at,
			badge: deletedCollectionBadge(r.kind)
		}));
		return { rows, ids: result.data, response: result.response };
	}

	async function load(which: DeletedTab, more = false) {
		const current = panes[which];
		if (more ? current.loadingMore : false) return;
		if (more) current.loadingMore = true;
		else {
			current.loading = true;
			current.rows = [];
		}
		current.error = null;
		try {
			const page = await fetchPage(which, more ? current.cursor : null);
			if ('error' in page) current.error = page.error ?? 'Something went wrong.';
			else {
				current.rows = more ? [...current.rows, ...page.rows] : page.rows;
				const total = Number(page.response?.headers.get('total-count'));
				current.total =
					Number.isFinite(total) && page.response?.headers.has('total-count') ? total : null;
				current.cursor = nextCursor(page.response?.headers.get('link'), page.ids);
			}
		} catch {
			current.error = 'Could not load the list. Check your connection and try again.';
		}
		now = new Date();
		current.loading = false;
		current.loadingMore = false;
	}

	$effect(() => {
		void load('items');
		void load('collections');
		void fetchAllNodeTypes().then((types) => {
			if (types) typeLabels = Object.fromEntries(types.map((t) => [t.slug, t.label]));
		});
	});

	async function removeRow(which: DeletedTab, id: string) {
		const target = panes[which];
		target.rows = target.rows.filter((r) => r.id !== id);
		if (target.total !== null) target.total = Math.max(0, target.total - 1);
		await tick();
		listEl?.focus();
	}

	async function handleRestore(row: Row) {
		if (busyId) return;
		busyId = row.id;
		actionError = null;
		const which = tab;
		try {
			const result =
				which === 'items'
					? await restoreNode({ path: { node_id: row.id } })
					: await restoreCollection({ path: { collection_id: row.id } });
			if (result.error) {
				actionError = {
					id: row.id,
					message: deletedActionError(
						'restore',
						result.response?.status,
						errorMessage(result.error)
					)
				};
			} else {
				await removeRow(which, row.id);
				toast.success(`${row.name} restored`);
			}
		} catch {
			actionError = { id: row.id, message: deletedActionError('restore', undefined, '') };
		} finally {
			busyId = null;
		}
	}

	async function handlePurge() {
		if (!purgeTarget || busyId) return;
		const { tab: which, row } = purgeTarget;
		busyId = row.id;
		actionError = null;
		try {
			const result =
				which === 'items'
					? await purgeNode({ path: { node_id: row.id } })
					: await purgeCollection({ path: { collection_id: row.id } });
			if (result.error) {
				actionError = {
					id: row.id,
					message: deletedActionError('purge', result.response?.status, errorMessage(result.error))
				};
			} else {
				await removeRow(which, row.id);
				toast.success(`${row.name} permanently deleted`);
			}
		} catch {
			actionError = { id: row.id, message: deletedActionError('purge', undefined, '') };
		} finally {
			purgeTarget = null;
			busyId = null;
		}
	}

	const tabs: { id: DeletedTab; label: string }[] = [
		{ id: 'items', label: 'Items' },
		{ id: 'collections', label: 'Collections' }
	];
</script>

<svelte:head>
	<title>Recently deleted - Menagerist</title>
</svelte:head>

{#snippet collectionBadge(row: Row)}
	{#if row.badge === 'Smart'}
		<Badge variant="secondary" class="shrink-0">Smart</Badge>
	{:else if row.badge === 'List'}
		<Badge variant="outline" class="shrink-0">List</Badge>
	{/if}
{/snippet}

{#snippet rowActions(row: Row, compact: boolean)}
	{#if canRestore}
		<Button
			type="button"
			variant="outline"
			class={compact ? 'h-9' : 'h-11 flex-1 sm:flex-none'}
			disabled={busyId !== null}
			aria-label="Restore {row.name}"
			onclick={() => void handleRestore(row)}
		>
			{#if busyId === row.id && purgeTarget === null}
				<Spinner class="size-4" />
			{:else}
				<RotateCcw class="size-4" aria-hidden="true" />
			{/if}
			Restore
		</Button>
	{/if}
	{#if canPurge}
		<Button
			type="button"
			variant="outline"
			class={compact ? 'h-9' : 'h-11 flex-1 sm:flex-none'}
			disabled={busyId !== null}
			aria-label="Purge {row.name}"
			onclick={() => (purgeTarget = { tab, row })}
		>
			<Trash2 class="size-4" aria-hidden="true" />
			Purge
		</Button>
	{/if}
{/snippet}

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-4xl flex-col gap-6">
		<BackButton fallback={resolve('/settings')} />
		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Recently deleted</h1>
			<p class="mt-1 text-muted-foreground">
				Restore something you deleted, or delete it for good.
			</p>
		</div>

		<div class="flex gap-2" role="group" aria-label="Show">
			{#each tabs as t (t.id)}
				<Button
					type="button"
					variant={tab === t.id ? 'secondary' : 'outline'}
					class="h-11 flex-1 sm:flex-none"
					aria-pressed={tab === t.id}
					onclick={() => {
						tab = t.id;
						actionError = null;
					}}
				>
					{t.label}
					{#if panes[t.id].total !== null}
						<span class="text-muted-foreground">({panes[t.id].total})</span>
					{/if}
				</Button>
			{/each}
		</div>

		{#if pane.error}
			<Alert.Root variant="destructive">
				<Alert.Description>{pane.error}</Alert.Description>
			</Alert.Root>
			<Button type="button" variant="outline" class="h-11 w-fit" onclick={() => void load(tab)}>
				Retry
			</Button>
		{:else if pane.loading}
			<div class="space-y-3" aria-busy="true">
				<Skeleton class="h-20 w-full rounded-xl" />
				<Skeleton class="h-20 w-full rounded-xl" />
			</div>
		{:else if pane.rows.length === 0}
			<p class="text-sm text-muted-foreground" bind:this={listEl} tabindex="-1">
				{NOTHING_DELETED_MESSAGE}
			</p>
		{:else}
			<div class="outline-none" bind:this={listEl} tabindex="-1">
				{#if wide.current}
					<DataTable
						label={tab === 'items' ? 'Deleted items' : 'Deleted collections'}
						columns={[
							{ label: 'Name' },
							...(tab === 'items' ? [{ label: 'Type' }] : []),
							{ label: 'When' },
							...(canRestore || canPurge ? [{ label: 'Actions', end: true }] : [])
						]}
					>
						{#each pane.rows as row (row.id)}
							<Table.Row>
								<Table.Cell class="max-w-sm">
									<div class="flex items-center gap-2">
										<p class="truncate font-medium" title={row.name}>{row.name}</p>
										{@render collectionBadge(row)}
									</div>
									{#if actionError?.id === row.id}
										<p class="mt-1 text-sm text-destructive" role="alert">{actionError.message}</p>
									{/if}
								</Table.Cell>
								{#if tab === 'items'}
									<Table.Cell class="text-muted-foreground">
										{deletedItemType(row.type, typeLabels) ?? '—'}
									</Table.Cell>
								{/if}
								<Table.Cell class="text-muted-foreground">
									<time datetime={row.deletedAt} title={formatDateTime(row.deletedAt).local}>
										{describeDeleted(row.deletedAt, now)}
									</time>
								</Table.Cell>
								{#if canRestore || canPurge}
									<Table.Cell>
										<div class="flex justify-end gap-2">
											{@render rowActions(row, true)}
										</div>
									</Table.Cell>
								{/if}
							</Table.Row>
						{/each}
					</DataTable>
				{:else}
					<ul
						class="space-y-3"
						aria-label={tab === 'items' ? 'Deleted items' : 'Deleted collections'}
					>
						{#each pane.rows as row (row.id)}
							{@const type = deletedItemType(row.type, typeLabels)}
							<li>
								<Card.Root>
									<Card.Content
										class="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
									>
										<div class="min-w-0 space-y-1">
											<div class="flex items-center gap-2">
												<p class="truncate font-medium" title={row.name}>{row.name}</p>
												{@render collectionBadge(row)}
											</div>
											<p class="text-xs text-muted-foreground">
												{#if type}{type} &middot;{/if}
												{describeDeleted(row.deletedAt, now)}
											</p>
											{#if actionError?.id === row.id}
												<p class="text-sm text-destructive" role="alert">{actionError.message}</p>
											{/if}
										</div>
										{#if canRestore || canPurge}
											<div class="flex shrink-0 gap-2">
												{@render rowActions(row, false)}
											</div>
										{/if}
									</Card.Content>
								</Card.Root>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
			{#if pane.cursor}
				<Button
					type="button"
					variant="outline"
					class="h-11 w-fit"
					disabled={pane.loadingMore}
					onclick={() => void load(tab, true)}
				>
					{#if pane.loadingMore}<Spinner class="size-4" />{/if}
					Load more
				</Button>
			{/if}
		{/if}
	</div>
</main>

<ConfirmDialog
	open={purgeTarget !== null}
	title="Delete for good?"
	description={purgeTarget ? purgeDescription(purgeTarget.row.name) : ''}
	confirmLabel="Purge"
	busyLabel="Deleting…"
	busy={busyId !== null && purgeTarget !== null}
	onOpenChange={(open) => {
		if (!open && busyId === null) purgeTarget = null;
	}}
	onConfirm={() => void handlePurge()}
/>
