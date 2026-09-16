<script lang="ts">
	import { Dialog } from 'bits-ui';
	import { Camera, X } from '@lucide/svelte';
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { captureController, type StagedPhoto } from '$lib/capture.svelte.js';
	import { createNode, stageMedia, attachMedia } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import CategorySelect from '$lib/components/category-select.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';

	let name = $state('');
	let selectedType = $state<string | null>(null);
	let saving = $state(false);
	let stagedAsset = $state<StagedPhoto | null>(null);
	let staging = $state(false);

	async function handlePhotoChange(e: Event) {
		const file = (e.target as HTMLInputElement).files?.[0] ?? null;
		if (!file) return;
		staging = true;
		const previewUrl = URL.createObjectURL(file);
		const result = await stageMedia({ body: { file } });
		if (result.error || !result.data) {
			URL.revokeObjectURL(previewUrl);
			toast.error("Couldn't add photo", { description: errorMessage(result.error) });
			staging = false;
			return;
		}
		stagedAsset = { id: result.data.id, filename: result.data.filename, previewUrl };
		staging = false;
	}

	function clearPhoto() {
		if (stagedAsset) URL.revokeObjectURL(stagedAsset.previewUrl);
		stagedAsset = null;
	}

	async function save() {
		if (!name.trim() || saving) return;
		saving = true;
		const result = await createNode({ body: { name: name.trim(), type: selectedType || null } });
		if (result.error || !result.data) {
			toast.error("Couldn't save", { description: errorMessage(result.error) });
			saving = false;
			return;
		}
		if (stagedAsset) {
			await attachMedia({
				path: { asset_id: stagedAsset.id },
				body: { target_type: 'node', target_id: result.data.id, attribute_key: 'cover' }
			});
		}
		captureController.notifyNodeCreated();
		saving = false;
		close();
	}

	function openFullForm() {
		captureController.setPendingHandoff({ name, selectedType, stagedPhoto: stagedAsset });
		captureController.hide();
		name = '';
		selectedType = null;
		stagedAsset = null;
		void goto(resolve('/collection/new'));
	}

	function close() {
		captureController.hide();
		resetState();
	}

	function resetState() {
		name = '';
		selectedType = null;
		if (stagedAsset) URL.revokeObjectURL(stagedAsset.previewUrl);
		stagedAsset = null;
	}
</script>

<Dialog.Root
	open={captureController.open}
	onOpenChange={(v) => {
		if (!v) close();
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
		<Dialog.Content
			class="fixed right-0 bottom-0 left-0 z-50 max-h-[90dvh] overflow-y-auto rounded-t-2xl border-t bg-background p-6 shadow-xl sm:inset-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-full sm:max-w-lg sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border"
		>
			<!-- Drag handle (mobile only) -->
			<div class="mx-auto mb-5 h-1.5 w-12 rounded-full bg-muted sm:hidden"></div>

			<div class="flex items-center justify-between">
				<Dialog.Title class="text-lg font-semibold">Quick capture</Dialog.Title>
				<button
					onclick={close}
					class="rounded-md p-1 text-muted-foreground hover:text-foreground"
					aria-label="Close"
				>
					<X class="size-4" />
				</button>
			</div>

			<div class="mt-4 space-y-4">
				<!-- Photo -->
				{#if stagedAsset}
					<div class="relative">
						<img
							src={stagedAsset.previewUrl}
							alt="Photo preview"
							class="max-h-48 w-full rounded-lg object-cover"
						/>
						<button
							type="button"
							onclick={clearPhoto}
							aria-label="Remove photo"
							class="absolute top-2 right-2 rounded-full bg-black/50 p-1 text-white hover:bg-black/70"
						>
							<X class="size-3" />
						</button>
					</div>
				{:else}
					<label
						class="flex cursor-pointer items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border px-4 py-4 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground {staging
							? 'pointer-events-none opacity-60'
							: ''}"
					>
						<Camera class="size-4" />
						{staging ? 'Adding…' : 'Add photo'}
						<!-- @ts-expect-error capture is a valid mobile HTML attribute -->
						<input
							type="file"
							accept="image/*"
							capture="environment"
							class="sr-only"
							disabled={staging}
							onchange={handlePhotoChange}
						/>
					</label>
				{/if}

				<!-- Name -->
				<Input
					bind:value={name}
					placeholder="Name…"
					autofocus
					onkeydown={(e) => {
						if (e.key === 'Enter') void save();
					}}
				/>

				<!-- Category -->
				<div class="space-y-1.5">
					<Label class="text-xs text-muted-foreground">Category</Label>
					<CategorySelect bind:value={selectedType} />
				</div>

				<!-- Footer -->
				<div class="flex items-center justify-between">
					<button
						type="button"
						onclick={openFullForm}
						class="text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
					>
						Use full form →
					</button>
					<Button onclick={save} disabled={!name.trim() || saving}>
						{saving ? 'Saving…' : 'Save'}
					</Button>
				</div>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
