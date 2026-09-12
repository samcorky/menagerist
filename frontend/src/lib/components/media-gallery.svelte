<script lang="ts">
	import { Upload, X, File as FileIcon, Star, StarOff } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { SvelteSet } from 'svelte/reactivity';
	import {
		listNodeMedia,
		uploadAndAttachMedia,
		deleteMedia,
		attachMedia,
		detachMedia,
		type NodeMediaItemResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';

	let { nodeId }: { nodeId: string } = $props();

	type UploadingEntry = { id: string; name: string; progress: 'uploading' | 'error' };

	let assets = $state<NodeMediaItemResponse[]>([]);
	let uploading = $state<UploadingEntry[]>([]);
	let loading = $state(true);
	let dragOver = $state(false);
	let fileInputEl = $state<HTMLInputElement | null>(null);
	let dropZoneEl = $state<HTMLDivElement | null>(null);

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

	async function loadMedia() {
		loading = true;
		const result = await listNodeMedia({ path: { node_id: nodeId } });
		if (result.data) assets = result.data;
		loading = false;
	}

	$effect(() => {
		void loadMedia();
	});

	async function uploadFiles(files: FileList | File[]) {
		const list = Array.from(files);
		if (list.length === 0) return;

		const entries: UploadingEntry[] = list.map((f) => ({
			id: crypto.randomUUID(),
			name: f.name,
			progress: 'uploading'
		}));
		uploading = [...uploading, ...entries];

		await Promise.all(
			list.map(async (file, i) => {
				const entry = entries[i];

				const fileIsImage = file.type.startsWith('image/');
				const hasCover = coverIds.size > 0;
				const attributeKey: 'cover' | undefined = fileIsImage && !hasCover ? 'cover' : undefined;

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
					await loadMedia();
				}
			})
		);
	}

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		if (e.dataTransfer?.files) void uploadFiles(e.dataTransfer.files);
	}

	function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		if (input.files) void uploadFiles(input.files);
		input.value = '';
	}

	function handleDelete(asset: NodeMediaItemResponse, triggerEl: HTMLElement) {
		const tile = triggerEl.closest<HTMLElement>('.group');
		const focusTarget =
			tile?.nextElementSibling?.querySelector<HTMLElement>('button[aria-label^="Delete"]') ??
			tile?.previousElementSibling?.querySelector<HTMLElement>('button[aria-label^="Delete"]') ??
			dropZoneEl;

		const removed = assets.filter((a) => a.id === asset.id);
		assets = assets.filter((a) => a.id !== asset.id);
		focusTarget?.focus();

		let undone = false;
		const timerId = setTimeout(async () => {
			if (undone) return;
			const result = await deleteMedia({ path: { asset_id: asset.id } });
			if (result.error) {
				assets = [...assets, ...removed];
				toast.error('Delete failed', { description: errorMessage(result.error) });
			}
		}, 5000);

		toast('File deleted', {
			action: {
				label: 'Undo',
				onClick: () => {
					undone = true;
					clearTimeout(timerId);
					assets = [...assets, ...removed];
				}
			},
			duration: 5000
		});
	}

	async function setCover(asset: NodeMediaItemResponse) {
		const currentCoverId = [...coverIds].find((id) => id !== asset.id);
		if (currentCoverId) {
			await detachMedia({
				path: { asset_id: currentCoverId },
				body: { target_type: 'node', target_id: nodeId, attribute_key: 'cover' }
			});
		}
		await attachMedia({
			path: { asset_id: asset.id },
			body: { target_type: 'node', target_id: nodeId, attribute_key: 'cover' }
		});
		await loadMedia();
	}

	async function removeCover(asset: NodeMediaItemResponse) {
		await detachMedia({
			path: { asset_id: asset.id },
			body: { target_type: 'node', target_id: nodeId, attribute_key: 'cover' }
		});
		await loadMedia();
	}

	function isImage(asset: NodeMediaItemResponse) {
		return asset.content_type.startsWith('image/');
	}

	function formatSize(bytes: number) {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}
</script>

<div class="space-y-3">
	<!-- Drop zone -->
	<div
		bind:this={dropZoneEl}
		role="button"
		tabindex="0"
		class="relative flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed py-6 text-sm transition-colors {dragOver
			? 'border-primary bg-primary/5'
			: 'border-border hover:border-primary/50 hover:bg-muted/40'}"
		ondragover={(e) => {
			e.preventDefault();
			dragOver = true;
		}}
		ondragleave={() => (dragOver = false)}
		ondrop={handleDrop}
		onclick={() => fileInputEl?.click()}
		onkeydown={(e) => e.key === 'Enter' && fileInputEl?.click()}
	>
		<Upload class="size-5 text-muted-foreground" />
		<span class="text-muted-foreground">
			Drop files here or <span class="text-foreground underline underline-offset-2">browse</span>
		</span>
		<input
			bind:this={fileInputEl}
			type="file"
			multiple
			class="sr-only"
			onchange={handleFileInput}
		/>
	</div>

	<!-- Loading skeleton -->
	{#if loading}
		<div class="grid grid-cols-3 gap-2 sm:grid-cols-4">
			{#each [1, 2, 3] as s (s)}
				<div class="aspect-square animate-pulse rounded-lg bg-muted"></div>
			{/each}
		</div>
	{:else if displayAssets.length > 0 || uploading.length > 0}
		<div class="grid grid-cols-3 gap-2 sm:grid-cols-4">
			<!-- In-flight uploads -->
			{#each uploading as u (u.id)}
				<div
					class="relative flex aspect-square flex-col items-center justify-center gap-1.5 rounded-lg border bg-muted/50 p-2 text-center {u.progress ===
					'error'
						? 'border-destructive/50'
						: ''}"
				>
					<div
						class="size-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground {u.progress ===
						'error'
							? 'hidden'
							: ''}"
					></div>
					{#if u.progress === 'error'}
						<X class="size-4 text-destructive" />
					{/if}
					<span class="line-clamp-2 text-xs text-muted-foreground">{u.name}</span>
				</div>
			{/each}

			<!-- Uploaded assets -->
			{#each displayAssets as asset (asset.id)}
				<div class="group relative aspect-square overflow-hidden rounded-lg border bg-muted/30">
					{#if isImage(asset)}
						<img
							src={asset.content_url}
							alt={asset.filename}
							class="h-full w-full object-cover"
							loading="lazy"
						/>
						<!-- Cover badge -->
						{#if coverIds.has(asset.id)}
							<div class="absolute top-1 left-1 rounded-full bg-black/60 p-0.5">
								<Star class="size-3 fill-yellow-400 text-yellow-400" />
							</div>
						{/if}
					{:else}
						<div class="flex h-full flex-col items-center justify-center gap-1.5 p-2 text-center">
							<FileIcon class="size-6 text-muted-foreground" />
							<span class="line-clamp-2 text-xs text-muted-foreground">{asset.filename}</span>
							<span class="text-xs text-muted-foreground/60">{formatSize(asset.size)}</span>
						</div>
					{/if}

					<!-- Hover overlay -->
					<div
						class="absolute inset-0 flex flex-col items-end justify-start gap-1 bg-black/0 p-1 transition-colors group-hover:bg-black/40"
					>
						{#if isImage(asset)}
							{#if coverIds.has(asset.id)}
								<button
									type="button"
									onclick={() => removeCover(asset)}
									class="rounded-full bg-black/70 p-1 text-yellow-400 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-black/90"
									aria-label="Remove cover for {asset.filename}"
								>
									<StarOff class="size-3" />
								</button>
							{:else}
								<button
									type="button"
									onclick={() => setCover(asset)}
									class="rounded-full bg-black/70 p-1 text-white opacity-0 transition-opacity group-hover:opacity-100 hover:bg-black/90"
									aria-label="Set as cover {asset.filename}"
								>
									<Star class="size-3" />
								</button>
							{/if}
						{/if}
						<button
							type="button"
							onclick={(e) => handleDelete(asset, e.currentTarget)}
							class="rounded-full bg-black/70 p-1 text-white opacity-0 transition-opacity group-hover:opacity-100 hover:bg-black/90"
							aria-label="Delete {asset.filename}"
						>
							<X class="size-3" />
						</button>
					</div>
				</div>
			{/each}
		</div>
	{:else}
		<p class="text-center text-xs text-muted-foreground">No files attached yet.</p>
	{/if}
</div>
