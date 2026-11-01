<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { Download, Plus, Trash2 } from '@lucide/svelte';
	import {
		client,
		deleteUserExport,
		exportUserData,
		listUserExports,
		type UserExportResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { formatDateTime } from '$lib/format-date';
	import { wide } from '$lib/viewport.svelte';
	import {
		NO_EXPORTS_MESSAGE,
		describeExportExpiry,
		formatExportSize
	} from '$lib/personal-exports';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import DataTable from '$lib/components/data-table.svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';
	import * as Table from '$lib/components/ui/table/index.js';

	let exports = $state<UserExportResponse[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);
	let creating = $state(false);
	let createError = $state<string | null>(null);
	let deleteTarget = $state<UserExportResponse | null>(null);
	let deleting = $state(false);
	let deleteError = $state<string | null>(null);
	let now = $state(new Date());

	async function load() {
		loading = true;
		loadError = null;
		try {
			const result = await listUserExports();
			if (result.error || !result.data) loadError = networkAwareError(result).title;
			else exports = result.data;
		} catch {
			loadError = 'Could not load exports.';
		}
		now = new Date();
		loading = false;
	}

	$effect(() => {
		void load();
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
				await load();
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
			const result = await deleteUserExport({ path: { backup_id: deleteTarget.id } });
			if (result.error) {
				deleteError = errorMessage(result.error);
				toast.error(deleteError);
			} else {
				toast.success('Export deleted');
			}
			deleteTarget = null;
			await load();
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
			url: '/api/v1/me/export/{backup_id}/download',
			path: { backup_id: id }
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

	{#if loadError}
		<Alert.Root variant="destructive">
			<Alert.Description>{loadError}</Alert.Description>
		</Alert.Root>
		<Button type="button" variant="outline" class="pointer-coarse:h-11" onclick={() => void load()}
			>Retry</Button
		>
	{:else if loading && exports.length === 0}
		<Skeleton class="h-20 w-full rounded-xl" />
	{:else if exports.length === 0}
		<p class="text-sm text-muted-foreground">{NO_EXPORTS_MESSAGE}</p>
	{:else}
		{#if wide.current}
			<DataTable
				label="Exports"
				columns={[
					{ label: 'Created' },
					{ label: 'Size' },
					{ label: 'Expires' },
					{ label: 'Actions', end: true }
				]}
			>
				{#each exports as item (item.id)}
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
				{/each}
			</DataTable>
		{:else}
			<ul class="space-y-3" aria-label="Exports">
				{#each exports as item (item.id)}
					{@const created = formatDateTime(item.created_at)}
					<li>
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
					</li>
				{/each}
			</ul>
		{/if}
	{/if}
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
