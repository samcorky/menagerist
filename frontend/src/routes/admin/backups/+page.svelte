<script lang="ts">
	import { resolve } from '$app/paths';
	import { tick, untrack } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		client,
		createBackup,
		listBackups,
		uploadBackup,
		verifyBackup,
		deleteBackup,
		type BackupResponse,
		type VerificationResponse
	} from '$lib/api/client';
	import { networkAwareError, uploadErrorMessage } from '$lib/api/errors';
	import { auth } from '$lib/auth.svelte.js';
	import { formatDateTime } from '$lib/format-date';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import BackButton from '$lib/components/back-button.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';

	const canRead = $derived(auth.can('backup:archive:read'));
	const canCreate = $derived(auth.can('backup:archive:create'));
	const canDelete = $derived(auth.can('backup:archive:delete'));
	let backups = $state.raw<BackupResponse[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let busy = $state<string | null>(null);
	let label = $state('manual');
	let uploadOpen = $state(false);
	let files = $state<FileList>();
	let uploadError = $state<string | null>(null);
	let deleteTarget = $state<BackupResponse | null>(null);
	let deleteError = $state<string | null>(null);
	let reports = $state<Record<string, VerificationResponse>>({});
	let rowErrors = $state<Record<string, string>>({});
	let createButton = $state<HTMLButtonElement | null>(null);
	const loadingDisplay = delayedLoading();
	$effect(() => loadingDisplay.set(loading));
	$effect(() => {
		if (canRead) untrack(() => void load());
		else loading = false;
	});

	async function load() {
		loading = true;
		error = null;
		try {
			const result = await listBackups();
			if (result.error || !result.data) error = networkAwareError(result).title;
			else backups = result.data;
		} catch {
			error = 'Could not load backups. Check your connection and try again.';
		} finally {
			loading = false;
		}
	}
	async function create(event: SubmitEvent) {
		event.preventDefault();
		if (busy || !canCreate) return;
		busy = 'create';
		error = null;
		try {
			const result = await createBackup({ body: { label: label.trim() || 'manual' } });
			if (result.error || !result.data) error = networkAwareError(result).title;
			else {
				backups = [result.data, ...backups];
				toast.success('Backup created');
			}
		} catch {
			error = 'Could not create backup. Try again.';
		} finally {
			busy = null;
		}
	}
	async function upload(event: SubmitEvent) {
		event.preventDefault();
		const file = files?.[0];
		if (!file || busy || !canCreate) return;
		busy = 'upload';
		uploadError = null;
		try {
			const result = await uploadBackup({ body: file });
			if (result.error || !result.data) uploadError = uploadErrorMessage(result);
			else {
				backups = [result.data, ...backups.filter((b) => b.id !== result.data.id)];
				uploadOpen = false;
				files = undefined;
				toast.success('Backup uploaded');
			}
		} catch {
			uploadError = 'Could not upload backup. Check your connection and try again.';
		} finally {
			busy = null;
		}
	}
	async function verify(backup: BackupResponse) {
		if (busy) return;
		busy = backup.id;
		delete rowErrors[backup.id];
		delete reports[backup.id];
		try {
			const result = await verifyBackup({ path: { backup_id: backup.id } });
			if (result.error || !result.data) rowErrors[backup.id] = networkAwareError(result).title;
			else reports[backup.id] = result.data;
		} catch {
			rowErrors[backup.id] = 'Could not verify backup. Try again.';
		} finally {
			busy = null;
		}
	}
	async function remove() {
		if (!deleteTarget || busy || !canDelete) return;
		const id = deleteTarget.id;
		busy = 'delete';
		deleteError = null;
		try {
			const result = await deleteBackup({ path: { backup_id: id } });
			if (result.error) deleteError = networkAwareError(result).title;
			else {
				backups = backups.filter((b) => b.id !== id);
				deleteTarget = null;
				toast.success('Backup deleted');
				busy = null;
				await tick();
				createButton?.focus();
			}
		} catch {
			deleteError = 'Could not delete backup. Try again.';
		} finally {
			busy = null;
		}
	}
	function size(bytes: number) {
		return bytes < 1048576
			? `${(bytes / 1024).toFixed(1)} KB`
			: `${(bytes / 1048576).toFixed(1)} MB`;
	}
	function downloadUrl(id: string) {
		return client.buildUrl({ url: '/api/v1/backup/{backup_id}/download', path: { backup_id: id } });
	}
</script>

<svelte:head><title>Backups - Menagerist</title></svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-3xl flex-col gap-6">
		<BackButton fallback={resolve('/admin')} />
		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Backups</h1>
			<p class="mt-1 text-muted-foreground">
				Keep a complete copy of this Menagerist, including accounts, collection content and images.
			</p>
		</div>
		{#if !canRead}
			<Alert.Root
				><Alert.Description>Only administrators can manage backups.</Alert.Description></Alert.Root
			>
		{:else}
			{#if canCreate}
				<form onsubmit={create} class="flex flex-col gap-3 sm:flex-row sm:items-end">
					<div class="flex-1 space-y-2">
						<Label for="backup-label">Backup label</Label><Input
							id="backup-label"
							bind:value={label}
							maxlength={120}
							class="h-11"
							disabled={loading || busy !== null}
						/>
					</div>
					<Button
						type="submit"
						bind:ref={createButton}
						class="h-11"
						disabled={loading || busy !== null}
						>{busy === 'create' ? 'Creating backup...' : 'Create backup'}</Button
					>
				</form>
			{/if}
			<div class="flex flex-wrap gap-2">
				{#if canCreate}<Button
						variant="outline"
						class="h-11"
						disabled={loading || busy !== null}
						onclick={() => {
							uploadError = null;
							uploadOpen = true;
						}}>Upload backup</Button
					>{/if}
				<Button variant="outline" class="h-11" disabled={loading || busy !== null} onclick={load}
					>Refresh</Button
				>
			</div>
			{#if error}<Alert.Root variant="destructive"
					><Alert.Description>{error}</Alert.Description><Button
						variant="outline"
						class="mt-2 h-11"
						disabled={loading || busy !== null}
						onclick={load}>Retry</Button
					></Alert.Root
				>{/if}
			{#if loadingDisplay.show}
				<div role="status" aria-label="Loading backups" class="space-y-3">
					<Skeleton class="h-40 w-full" /><Skeleton class="h-40 w-full" />
				</div>
			{:else if !loading && !error && backups.length === 0}
				<p class="rounded-xl border p-6 text-muted-foreground">
					No backups yet. Create a backup to keep a copy of this Menagerist.
				</p>
			{/if}
			<ul aria-label="Backups" class="space-y-4" aria-busy={loading}>
				{#each backups as backup (backup.id)}
					<li>
						<Card.Root>
							<Card.Header
								><Card.Title class="break-words">{backup.label}</Card.Title><Card.Description
									><time datetime={backup.created_at} title={formatDateTime(backup.created_at).utc}
										>{formatDateTime(backup.created_at).local}</time
									>
									- {size(backup.size)}</Card.Description
								></Card.Header
							>
							<Card.Content class="space-y-4">
								<dl class="grid gap-2 text-sm sm:grid-cols-2">
									<div>
										<dt class="text-muted-foreground">App version</dt>
										<dd class="break-all">{backup.app_version}</dd>
									</div>
									<div>
										<dt class="text-muted-foreground">Database version</dt>
										<dd class="break-all">{backup.alembic_revision}</dd>
									</div>
								</dl>
								<div class="flex flex-wrap gap-2">
									<Button href={downloadUrl(backup.id)} download variant="outline" class="h-11"
										>Download</Button
									><Button
										variant="outline"
										class="h-11"
										disabled={loading || busy !== null}
										onclick={() => verify(backup)}
										>{busy === backup.id ? 'Verifying...' : 'Verify'}</Button
									>{#if canDelete}<Button
											variant="outline"
											class="h-11 text-destructive"
											disabled={loading || busy !== null}
											onclick={() => {
												deleteError = null;
												deleteTarget = backup;
											}}>Delete</Button
										>{/if}
								</div>
								{#if rowErrors[backup.id]}<Alert.Root variant="destructive"
										><Alert.Description
											>{rowErrors[backup.id]} Use Verify to try again.</Alert.Description
										></Alert.Root
									>{/if}
								{#if reports[backup.id]}
									{#if reports[backup.id].findings.length === 0}<p role="status" class="text-sm">
											Backup verified
										</p>{:else}<Alert.Root variant="destructive"
											><Alert.Title>Backup verification failed</Alert.Title><Alert.Description
												><ul class="space-y-1">
													{#each reports[backup.id].findings as finding, index (index)}<li
															class="break-all"
														>
															{finding.kind.replaceAll('_', ' ')}: {finding.member}{#if finding.expected}
																(expected {finding.expected}; found {finding.actual ??
																	'missing'}){/if}
														</li>{/each}
												</ul></Alert.Description
											></Alert.Root
										>{/if}
								{/if}
							</Card.Content>
						</Card.Root>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</main>

<ResponsiveDialog.Root
	open={uploadOpen}
	onOpenChange={(open) => {
		if (!busy) uploadOpen = open;
	}}
>
	<ResponsiveDialog.Content title="Upload backup">
		<ResponsiveDialog.Description
			>Uploading stores an archive for later recovery. It does not replace any current content.</ResponsiveDialog.Description
		>
		<form onsubmit={upload} class="mt-4 space-y-4">
			<div class="space-y-2">
				<Label for="backup-archive">Backup archive</Label><input
					id="backup-archive"
					type="file"
					accept=".tar.gz,.gz,application/gzip"
					bind:files
					class="block min-h-11 w-full min-w-0 rounded-md border p-2 text-sm"
					disabled={loading || busy !== null}
				/>
			</div>
			{#if uploadError}<Alert.Root variant="destructive"
					><Alert.Description>{uploadError}</Alert.Description></Alert.Root
				>{/if}
			<div class="flex justify-end gap-2">
				<Button
					variant="outline"
					class="h-11"
					disabled={loading || busy !== null}
					onclick={() => (uploadOpen = false)}>Cancel</Button
				><Button type="submit" class="h-11" disabled={!files?.length || busy !== null}
					>{busy === 'upload' ? 'Uploading...' : 'Upload backup'}</Button
				>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
<ResponsiveDialog.Root
	open={deleteTarget !== null}
	onOpenChange={(open) => {
		if (!open && !busy) deleteTarget = null;
	}}
>
	<ResponsiveDialog.Content title="Delete backup" size="sm"
		><ResponsiveDialog.Description
			>Delete "{deleteTarget?.label}"? This permanently removes the stored archive. Download a copy
			first if you need to keep it.</ResponsiveDialog.Description
		>{#if deleteError}<Alert.Root variant="destructive" class="mt-4"
				><Alert.Description>{deleteError}</Alert.Description></Alert.Root
			>{/if}
		<div class="mt-4 flex justify-end gap-2">
			<Button
				variant="outline"
				class="h-11"
				disabled={loading || busy !== null}
				onclick={() => (deleteTarget = null)}>Cancel</Button
			><Button
				variant="destructive"
				class="h-11"
				disabled={loading || busy !== null}
				onclick={remove}>{busy === 'delete' ? 'Deleting...' : 'Delete backup'}</Button
			>
		</div></ResponsiveDialog.Content
	>
</ResponsiveDialog.Root>
