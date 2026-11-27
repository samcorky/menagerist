<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { Download, Plus, Trash2 } from '@lucide/svelte';
	import {
		client,
		deleteUserExport,
		exportUserData,
		listUserExports,
		type UserExportResponse,
		type UserExportSort
	} from '$lib/api/client';
	import { PagedList } from '$lib/paged-list.svelte';
	import { nextSort, sortQuery, type TableSort } from '$lib/table-sort';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { formatDateTime } from '$lib/format-date';
	import {
		NO_EXPORTS_MESSAGE,
		describeExportExpiry,
		formatExportSize
	} from '$lib/personal-exports';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import ListTable from '$lib/components/list-table.svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';
	import * as Table from '$lib/components/ui/table/index.js';

	// A person's exports are few, so they page ten at a time, with Previous and Next.
	const EXPORTS_PER_PAGE = 10;
	// The server sorts, so every page is in order, not only the one on screen.
	let sort = $state<TableSort<UserExportSort> | null>(null);
	const list = new PagedList<UserExportResponse, TableSort<UserExportSort> | null>(
		({ after, params }) =>
			listUserExports({ query: { after, limit: EXPORTS_PER_PAGE, ...sortQuery(params) } }),
		{ mode: 'page' }
	);
	const exports = $derived(list.rows);
	const loading = $derived(list.loading);
	let creating = $state(false);
	let createError = $state<string | null>(null);
	let deleteTarget = $state<UserExportResponse | null>(null);
	let deleting = $state(false);
	let deleteError = $state<string | null>(null);
	let now = $state(new Date());

	$effect(() => {
		void list.load(sort, { keepRows: true });
	});

	// The expiry text counts from when the page was read.
	$effect(() => {
		void list.rows;
		now = new Date();
	});

	async function handleCreate() {
		if (creating) return;
		creating = true;
		createError = null;
		try {
			const result = await exportUserData();
			if (result.error || !result.data) {
				createError = networkAwareError(result).title;
			} else {
				toast.success('Export created');
				// The newest is first.
				await list.load(sort, { keepRows: true });
			}
		} catch {
			createError = 'Could not create the export. Try again.';
		} finally {
			creating = false;
		}
	}

	async function handleDelete() {
		if (!deleteTarget || deleting) return;
		deleting = true;
		deleteError = null;
		try {
			const result = await deleteUserExport({ path: { export_id: deleteTarget.id } });
			if (result.error) {
				deleteError = errorMessage(result.error);
				toast.error(deleteError);
			} else {
				toast.success('Export deleted');
			}
			deleteTarget = null;
			await list.refresh();
		} catch {
			deleteError = 'Could not delete the export. Try again.';
			toast.error(deleteError);
			deleteTarget = null;
		} finally {
			deleting = false;
		}
	}

	function downloadUrl(id: string) {
		return client.buildUrl({
			url: '/api/v1/me/exports/{export_id}/download',
			path: { export_id: id }
		});
	}
</script>

<section class="space-y-4" aria-labelledby="exports-heading">
	<div class="flex flex-wrap items-center justify-between gap-2">
		<h2 id="exports-heading" class="font-heading text-lg font-semibold">Your data</h2>
		<Button
			type="button"
			variant="outline"
			class="pointer-coarse:h-11"
			disabled={creating}
			onclick={handleCreate}
		>
			{#if creating}
				<Spinner class="size-4" />
				Creating…
			{:else}
				<Plus class="size-4" aria-hidden="true" />
				Create export
			{/if}
		</Button>
	</div>
	<p class="text-sm text-muted-foreground">
		Download a copy of everything you have added. Exports are kept for 24 hours.
	</p>

	{#if createError}
		<Alert.Root variant="destructive">
			<Alert.Description>{createError}</Alert.Description>
		</Alert.Root>
	{/if}

	<ListTable
		label="Exports"
		what="your exports"
		columns={[
			{ label: 'Created', sortKey: 'created_at' },
			{ label: 'Size', sortKey: 'size' },
			{ label: 'Expires', sortKey: 'expires_at' },
			{ label: 'Actions', end: true }
		]}
		rows={exports}
		rowKey={(item) => item.id}
		{loading}
		failed={list.failed}
		onretry={() => void list.retry()}
		empty={NO_EXPORTS_MESSAGE}
		{sort}
		onsort={(key) => (sort = nextSort(sort, key as UserExportSort))}
		{list}
		noun="export"
		skeletons={1}
	>
		{#snippet row(item)}
			{@const created = formatDateTime(item.created_at)}
			<Table.Row>
				<Table.Cell class="font-medium" title={created.utc}>{created.local}</Table.Cell>
				<Table.Cell class="text-muted-foreground">{formatExportSize(item.size)}</Table.Cell>
				<Table.Cell class="text-muted-foreground">
					{describeExportExpiry(item.expires_at, now)}
				</Table.Cell>
				<Table.Cell>
					<div class="flex justify-end gap-2">
						<Button href={downloadUrl(item.id)} download variant="outline" class="h-9">
							<Download class="size-4" aria-hidden="true" />
							Download
						</Button>
						<Button
							type="button"
							variant="outline"
							class="h-9"
							onclick={() => (deleteTarget = item)}
						>
							<Trash2 class="size-4" aria-hidden="true" />
							Delete
						</Button>
					</div>
				</Table.Cell>
			</Table.Row>
		{/snippet}
		{#snippet card(item)}
			{@const created = formatDateTime(item.created_at)}
			<Card.Root>
				<Card.Content
					class="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between"
				>
					<div class="space-y-1">
						<p class="font-medium" title={created.utc}>{created.local}</p>
						<p class="text-xs text-muted-foreground">
							{formatExportSize(item.size)} &middot;
							{describeExportExpiry(item.expires_at, now)}
						</p>
					</div>
					<div class="flex shrink-0 gap-2">
						<Button
							href={downloadUrl(item.id)}
							download
							variant="outline"
							class="flex-1 sm:flex-none pointer-coarse:h-11"
						>
							<Download class="size-4" aria-hidden="true" />
							Download
						</Button>
						<Button
							type="button"
							variant="outline"
							class="flex-1 sm:flex-none pointer-coarse:h-11"
							onclick={() => (deleteTarget = item)}
						>
							<Trash2 class="size-4" aria-hidden="true" />
							Delete
						</Button>
					</div>
				</Card.Content>
			</Card.Root>
		{/snippet}
	</ListTable>
</section>

<ConfirmDialog
	open={deleteTarget !== null}
	title="Delete this export?"
	description="The file is removed straight away. You can create a new export at any time."
	confirmLabel="Delete export"
	busyLabel="Deleting…"
	busy={deleting}
	onOpenChange={(open) => {
		if (!open && !deleting) deleteTarget = null;
	}}
	onConfirm={() => void handleDelete()}
/>
