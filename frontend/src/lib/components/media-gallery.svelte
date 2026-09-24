<script lang="ts">
	import { onDestroy } from 'svelte';
	import { Dialog } from 'bits-ui';
	import {
		X,
		File as FileIcon,
		Star,
		StarOff,
		Pencil,
		Download,
		Trash2,
		MoreVertical
	} from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { SvelteSet } from 'svelte/reactivity';
	import {
		listNodeMedia,
		uploadAndAttachMedia,
		deleteMedia,
		setMediaCover,
		clearMediaCover,
		updateMedia,
		type NodeMediaItemResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Attachment from '$lib/components/ui/attachment/index.js';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';
	import ConfirmDialog from './confirm-dialog.svelte';
	import FileDrop from './file-drop.svelte';

	let { nodeId }: { nodeId: string } = $props();

	type UploadingEntry = {
		id: string;
		name: string;
		progress: 'uploading' | 'error';
		previewUrl?: string;
	};

	let assets = $state<NodeMediaItemResponse[]>([]);
	let uploading = $state<UploadingEntry[]>([]);
	let loading = $state(true);
	let deleteTarget = $state<NodeMediaItemResponse | null>(null);
	let deleting = $state(false);
	let renameTarget = $state<NodeMediaItemResponse | null>(null);
	let renameValue = $state('');
	let renameSaving = $state(false);
	let renameInput = $state<HTMLInputElement | null>(null);

	let lightboxAsset = $state<NodeMediaItemResponse | null>(null);
	let lightboxFullLoaded = $state(false);

	function makeUploadId() {
		if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
			return crypto.randomUUID();
		}
		return `${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`;
	}

	$effect(() => {
		if (lightboxAsset) lightboxFullLoaded = false;
	});

	const displayAssets = $derived.by(() => {
		const seen = new SvelteSet<string>();
		const result: NodeMediaItemResponse[] = [];
		for (const asset of assets) {
			if (!seen.has(asset.id)) {
				seen.add(asset.id);
				result.push(asset);
			}
		}
		return result;
	});

	const coverIds = $derived(
		new SvelteSet(assets.filter((a) => a.attribute_key === 'cover').map((a) => a.id))
	);

	// Images render as media cards; everything else (PDFs, docs, ...) as a smaller row below.
	const displayImages = $derived(displayAssets.filter(isImage));
	const displayFiles = $derived(displayAssets.filter((a) => !isImage(a)));
	const uploadingImages = $derived(uploading.filter((u) => u.previewUrl !== undefined));
	const uploadingFiles = $derived(uploading.filter((u) => u.previewUrl === undefined));

	async function loadMedia() {
		loading = true;
		const result = await listNodeMedia({ path: { node_id: nodeId } });
		if (result.data) assets = result.data;
		loading = false;
	}

	$effect(() => {
		void loadMedia();
	});

	async function runWithConcurrency<T>(
		items: T[],
		limit: number,
		worker: (item: T, index: number) => Promise<void>
	): Promise<void> {
		let nextIndex = 0;
		async function runNext(): Promise<void> {
			while (nextIndex < items.length) {
				const index = nextIndex;
				nextIndex += 1;
				await worker(items[index], index);
			}
		}
		const poolSize = Math.min(limit, items.length);
		await Promise.all(Array.from({ length: poolSize }, () => runNext()));
	}

	async function uploadFiles(files: FileList | File[]) {
		const list = Array.from(files);
		if (list.length === 0) return;

		const entries: UploadingEntry[] = list.map((f) => ({
			id: makeUploadId(),
			name: f.name,
			progress: 'uploading',
			...(f.type.startsWith('image/') ? { previewUrl: URL.createObjectURL(f) } : {})
		}));
		uploading = [...uploading, ...entries];

		const hasExistingCover = coverIds.size > 0;
		const firstImageIndex = hasExistingCover
			? -1
			: list.findIndex((f) => f.type.startsWith('image/'));
		const attributeKeys: ('cover' | undefined)[] = list.map((_, i) =>
			i === firstImageIndex ? 'cover' : undefined
		);

		await runWithConcurrency(list, 3, async (file, i) => {
			const entry = entries[i];
			const attributeKey = attributeKeys[i];

			const result = await uploadAndAttachMedia({
				body: {
					file,
					target_type: 'node',
					target_id: nodeId,
					...(attributeKey ? { attribute_key: attributeKey } : {})
				}
			});

			if (result.error || !result.data) {
				uploading = uploading.map((u) => (u.id === entry.id ? { ...u, progress: 'error' } : u));
				toast.error(`Failed to upload ${file.name}`, { description: errorMessage(result.error) });
			} else {
				uploading = uploading.filter((u) => u.id !== entry.id);
				if (entry.previewUrl) URL.revokeObjectURL(entry.previewUrl);
				await loadMedia();
			}
		});
	}

	onDestroy(() => {
		for (const u of uploading) {
			if (u.previewUrl) URL.revokeObjectURL(u.previewUrl);
		}
	});

	async function confirmDelete() {
		const asset = deleteTarget;
		if (!asset) return;
		deleting = true;
		const removed = assets.filter((a) => a.id === asset.id);
		assets = assets.filter((a) => a.id !== asset.id);
		const result = await deleteMedia({ path: { asset_id: asset.id } });
		if (result.error) {
			assets = [...assets, ...removed];
			toast.error('Delete failed', { description: errorMessage(result.error) });
		}
		deleting = false;
		deleteTarget = null;
	}

	function downloadAsset(asset: NodeMediaItemResponse) {
		const a = document.createElement('a');
		a.href = asset.content_url;
		a.download = asset.filename;
		a.click();
	}

	async function setCover(asset: NodeMediaItemResponse) {
		const result = await setMediaCover({
			path: { asset_id: asset.id },
			body: { target_type: 'node', target_id: nodeId }
		});
		if (result.error) {
			toast.error('Failed to set cover', { description: errorMessage(result.error) });
			return;
		}
		await loadMedia();
	}

	async function removeCover(asset: NodeMediaItemResponse) {
		const result = await clearMediaCover({
			path: { asset_id: asset.id },
			body: { target_type: 'node', target_id: nodeId }
		});
		if (result.error) {
			toast.error('Failed to remove cover', { description: errorMessage(result.error) });
			return;
		}
		await loadMedia();
	}

	function startRename(asset: NodeMediaItemResponse) {
		renameTarget = asset;
		renameValue = asset.filename;
	}

	function cancelRename() {
		renameTarget = null;
	}

	async function saveRename(event?: SubmitEvent) {
		event?.preventDefault();
		const asset = renameTarget;
		if (!asset) return;
		const trimmed = renameValue.trim();
		if (!trimmed || trimmed === asset.filename) {
			cancelRename();
			return;
		}

		renameSaving = true;
		const result = await updateMedia({
			path: { asset_id: asset.id },
			body: { filename: trimmed }
		});
		renameSaving = false;

		if (result.response?.status === 412) {
			toast.error('Edit conflict', {
				description: 'This file was updated elsewhere — refresh to see the latest version.'
			});
		} else if (result.error || !result.data) {
			toast.error('Rename failed', { description: errorMessage(result.error) });
		} else {
			const updated = result.data;
			assets = assets.map((a) => (a.id === asset.id ? { ...a, ...updated } : a));
		}

		cancelRename();
	}

	$effect(() => {
		if (renameTarget) renameInput?.focus();
	});

	function isImage(asset: NodeMediaItemResponse) {
		return asset.content_type.startsWith('image/');
	}

	function formatSize(bytes: number) {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}
</script>

<div class="space-y-4">
	<FileDrop onFiles={uploadFiles} />

	<!-- Loading skeleton -->
	{#if loading}
		<div class="grid grid-cols-3 gap-3 sm:grid-cols-4">
			{#each [1, 2, 3] as s (s)}
				<div class="aspect-square animate-pulse rounded-2xl bg-muted"></div>
			{/each}
		</div>
	{:else if displayImages.length > 0 || displayFiles.length > 0 || uploading.length > 0}
		<!-- Images: media cards in a grid -->
		{#if displayImages.length > 0 || uploadingImages.length > 0}
			<div class="grid grid-cols-3 gap-3 sm:grid-cols-4">
				{#each uploadingImages as u (u.id)}
					<Attachment.Root orientation="vertical" state={u.progress} class="w-full">
						<Attachment.Media variant="image">
							<img src={u.previewUrl} alt={u.name} class="opacity-60" />
						</Attachment.Media>
						<Attachment.Content>
							<Attachment.Title>{u.name}</Attachment.Title>
							<Attachment.Description>
								{u.progress === 'error' ? 'Upload failed' : 'Uploading…'}
							</Attachment.Description>
						</Attachment.Content>
					</Attachment.Root>
				{/each}

				{#each displayImages as asset (asset.id)}
					<Attachment.Root orientation="vertical" state="done" class="w-full">
						<Attachment.Trigger
							onclick={() => (lightboxAsset = asset)}
							aria-label="View {asset.filename}"
						/>
						<Attachment.Media variant="image">
							<img
								src={asset.thumbnail_url ?? asset.content_url}
								alt={asset.filename}
								loading="lazy"
							/>
							{#if coverIds.has(asset.id)}
								<div
									class="pointer-events-none absolute top-1 left-1 rounded-full bg-black/60 p-0.5"
								>
									<Star class="size-3 fill-yellow-400 text-yellow-400" />
								</div>
							{/if}
						</Attachment.Media>
						<Attachment.Content>
							<Attachment.Title>{asset.filename}</Attachment.Title>
							<Attachment.Description>{formatSize(asset.size)}</Attachment.Description>
						</Attachment.Content>
						<Attachment.Actions>
							{#if coverIds.has(asset.id)}
								<Attachment.Action
									onclick={() => removeCover(asset)}
									aria-label="Remove cover for {asset.filename}"
								>
									<StarOff />
								</Attachment.Action>
							{:else}
								<Attachment.Action
									onclick={() => setCover(asset)}
									aria-label="Set as cover {asset.filename}"
								>
									<Star />
								</Attachment.Action>
							{/if}
							<DropdownMenu.Root>
								<DropdownMenu.Trigger>
									{#snippet child({ props })}
										<Attachment.Action {...props} aria-label="More actions for {asset.filename}">
											<MoreVertical />
										</Attachment.Action>
									{/snippet}
								</DropdownMenu.Trigger>
								<DropdownMenu.Content align="end">
									<DropdownMenu.Item onSelect={() => startRename(asset)}>
										<Pencil class="size-4" />
										Rename
									</DropdownMenu.Item>
									<DropdownMenu.Item onSelect={() => downloadAsset(asset)}>
										<Download class="size-4" />
										Download
									</DropdownMenu.Item>
									<DropdownMenu.Item variant="destructive" onSelect={() => (deleteTarget = asset)}>
										<Trash2 class="size-4" />
										Delete
									</DropdownMenu.Item>
								</DropdownMenu.Content>
							</DropdownMenu.Root>
						</Attachment.Actions>
					</Attachment.Root>
				{/each}
			</div>
		{/if}

		<!-- Other files: smaller rows below -->
		{#if displayFiles.length > 0 || uploadingFiles.length > 0}
			<div class="flex flex-col gap-2">
				{#each uploadingFiles as u (u.id)}
					<Attachment.Root size="sm" state={u.progress} class="w-full">
						<Attachment.Media>
							{#if u.progress === 'error'}
								<X class="text-destructive" />
							{:else}
								<Spinner />
							{/if}
						</Attachment.Media>
						<Attachment.Content>
							<Attachment.Title>{u.name}</Attachment.Title>
							<Attachment.Description>
								{u.progress === 'error' ? 'Upload failed' : 'Uploading…'}
							</Attachment.Description>
						</Attachment.Content>
					</Attachment.Root>
				{/each}

				{#each displayFiles as asset (asset.id)}
					<Attachment.Root size="sm" state="done" class="w-full">
						<Attachment.Media>
							<FileIcon />
						</Attachment.Media>
						<Attachment.Content>
							<Attachment.Title>{asset.filename}</Attachment.Title>
							<Attachment.Description>{formatSize(asset.size)}</Attachment.Description>
						</Attachment.Content>
						<Attachment.Actions>
							<DropdownMenu.Root>
								<DropdownMenu.Trigger>
									{#snippet child({ props })}
										<Attachment.Action {...props} aria-label="More actions for {asset.filename}">
											<MoreVertical />
										</Attachment.Action>
									{/snippet}
								</DropdownMenu.Trigger>
								<DropdownMenu.Content align="end">
									<DropdownMenu.Item onSelect={() => startRename(asset)}>
										<Pencil class="size-4" />
										Rename
									</DropdownMenu.Item>
									<DropdownMenu.Item onSelect={() => downloadAsset(asset)}>
										<Download class="size-4" />
										Download
									</DropdownMenu.Item>
									<DropdownMenu.Item variant="destructive" onSelect={() => (deleteTarget = asset)}>
										<Trash2 class="size-4" />
										Delete
									</DropdownMenu.Item>
								</DropdownMenu.Content>
							</DropdownMenu.Root>
						</Attachment.Actions>
					</Attachment.Root>
				{/each}
			</div>
		{/if}
	{:else}
		<p class="text-center text-xs text-muted-foreground">No files attached yet.</p>
	{/if}
</div>

<!-- Lightbox -->
{#if lightboxAsset}
	{@const asset = lightboxAsset}
	<div
		class="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/90 p-4"
		role="dialog"
		aria-modal="true"
		aria-label="Image viewer"
		onclick={() => (lightboxAsset = null)}
		onkeydown={(e) => e.key === 'Escape' && (lightboxAsset = null)}
		tabindex="-1"
	>
		<!-- eslint-disable svelte/no-navigation-without-resolve -->
		<a
			href={asset.content_url}
			download={asset.filename}
			class="absolute top-4 right-16 rounded-full bg-white/10 p-2 text-white after:absolute after:-inset-2 after:content-[''] hover:bg-white/20"
			aria-label="Download {asset.filename}"
		>
			<Download class="size-5" />
		</a>
		<!-- eslint-enable svelte/no-navigation-without-resolve -->
		<button
			type="button"
			class="absolute top-4 right-4 rounded-full bg-white/10 p-2 text-white after:absolute after:-inset-2 after:content-[''] hover:bg-white/20"
			onclick={() => (lightboxAsset = null)}
			aria-label="Close"
		>
			<X class="size-5" />
		</button>
		<div
			class="flex max-w-[90vw] flex-col items-center gap-2"
			onclick={(e) => e.stopPropagation()}
			role="presentation"
		>
			{#if asset.thumbnail_url && asset.content_url !== asset.thumbnail_url}
				<div class="grid w-full">
					<img
						src={asset.thumbnail_url}
						alt={asset.filename}
						class="col-start-1 row-start-1 max-h-[85dvh] w-full object-contain"
						aria-hidden="true"
					/>
					<img
						src={asset.content_url}
						alt={asset.filename}
						class="col-start-1 row-start-1 max-h-[85dvh] w-full object-contain transition-opacity duration-500 {lightboxFullLoaded
							? 'opacity-100'
							: 'opacity-0'}"
						onload={() => (lightboxFullLoaded = true)}
					/>
				</div>
			{:else}
				<img
					src={asset.content_url}
					alt={asset.filename}
					class="max-h-[85dvh] w-full object-contain"
				/>
			{/if}
			<p class="text-center text-sm text-white/60">{asset.filename}</p>
		</div>
	</div>
{/if}

<!-- Rename dialog -->
<Dialog.Root
	open={renameTarget !== null}
	onOpenChange={(v) => {
		if (!v) cancelRename();
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
		<Dialog.Content
			aria-label="Rename file"
			class="fixed right-0 bottom-0 left-0 z-50 max-h-[90dvh] overflow-y-auto rounded-t-2xl border-t bg-background p-6 shadow-xl sm:inset-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-full sm:max-w-sm sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border"
		>
			<div class="mx-auto mb-5 h-1.5 w-12 rounded-full bg-muted sm:hidden"></div>
			<div class="flex items-center justify-between">
				<Dialog.Title class="text-lg font-semibold">Rename file</Dialog.Title>
				<button
					type="button"
					onclick={cancelRename}
					class="relative rounded-md p-1 text-muted-foreground after:absolute after:-inset-2 after:content-[''] hover:text-foreground"
					aria-label="Close"
				>
					<X class="size-4" />
				</button>
			</div>
			<form class="mt-4 space-y-4" onsubmit={saveRename}>
				<Input
					bind:value={renameValue}
					bind:ref={renameInput}
					aria-label="Filename"
					onkeydown={(e) => {
						if (e.key === 'Escape') cancelRename();
					}}
				/>
				<div class="flex justify-end gap-2">
					<Button type="button" variant="outline" onclick={cancelRename}>Cancel</Button>
					<Button type="submit" disabled={renameSaving || !renameValue.trim()}>
						{renameSaving ? 'Saving…' : 'Save'}
					</Button>
				</div>
			</form>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<ConfirmDialog
	open={deleteTarget !== null}
	title="Delete file?"
	description={deleteTarget ? `${deleteTarget.filename} will be permanently deleted.` : undefined}
	busy={deleting}
	busyLabel="Deleting…"
	confirmLabel="Delete"
	onOpenChange={(v) => {
		if (!v) deleteTarget = null;
	}}
	onConfirm={confirmDelete}
/>
