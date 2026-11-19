<script lang="ts">
	import { Camera, ScanBarcode, X } from '@lucide/svelte';
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { captureController, type StagedPhoto } from '$lib/capture.svelte.js';
	import { createNode, stageMedia, attachMedia, type NodeTypeResponse } from '$lib/api/client';
	import { errorMessage, uploadErrorMessage } from '$lib/api/errors';
	import TypePicker from '$lib/components/type-picker.svelte';
	import BarcodeScanner from '$lib/components/barcode-scanner.svelte';
	import {
		NEW_BARCODE_DETAIL,
		scanFields,
		scannedAttributes,
		suggestScanField
	} from '$lib/barcode/scan-field';
	import { loadItemTypes } from '$lib/palette-sources';
	import type { AttributesSchema } from '$lib/schema-types';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { NativeSelect, NativeSelectOption } from '$lib/components/ui/native-select/index.js';

	let name = $state('');
	let selectedType = $state<string | null>(null);
	let creatingType = $state(false);
	let saving = $state(false);
	let stagedAsset = $state<StagedPhoto | null>(null);
	let staging = $state(false);
	let scannerOpen = $state(false);
	let code = $state<string | null>(null);
	let types = $state<NodeTypeResponse[]>([]);

	// Types are read only once a code is scanned, to offer the chosen type's fields.
	$effect(() => {
		if (code !== null)
			void loadItemTypes()
				.then((all) => (types = all))
				.catch(() => {});
	});

	const typeSchema = $derived(
		(types.find((type) => type.slug === selectedType)?.attributes_schema as
			AttributesSchema | null | undefined) ?? null
	);
	const codeFields = $derived(scanFields(typeSchema));
	// Follows the type until the person picks a field themselves.
	let codeField = $derived(suggestScanField(codeFields) ?? NEW_BARCODE_DETAIL);

	function scanned() {
		return code === null ? null : scannedAttributes(code, codeField, typeSchema);
	}

	async function handlePhotoChange(e: Event) {
		const file = (e.target as HTMLInputElement).files?.[0] ?? null;
		if (!file) return;
		staging = true;
		const previewUrl = URL.createObjectURL(file);
		const result = await stageMedia({ body: { file } });
		if (result.error || !result.data) {
			URL.revokeObjectURL(previewUrl);
			toast.error("Couldn't add photo", { description: uploadErrorMessage(result) });
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
		if (!name.trim() || saving || creatingType) return;
		saving = true;
		const barcode = scanned();
		const result = await createNode({
			body: {
				name: name.trim(),
				type: selectedType || null,
				...(barcode && { attributes: barcode.attributes, extra_schema: barcode.extraSchema })
			}
		});
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
		captureController.setPendingHandoff({
			name,
			selectedType,
			stagedPhoto: stagedAsset,
			barcode: scanned()
		});
		captureController.hide();
		name = '';
		selectedType = null;
		stagedAsset = null;
		code = null;
		void goto(resolve('/items/new'));
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
		code = null;
	}
</script>

<ResponsiveDialog.Root
	open={captureController.open}
	onOpenChange={(v) => {
		if (!v) close();
	}}
>
	<ResponsiveDialog.Content title="Quick capture" size="lg">
		<div class="mt-4 space-y-4">
			<!-- Photo -->
			{#if stagedAsset}
				<div class="relative">
					<img
						src={stagedAsset.previewUrl}
						alt="Preview"
						class="max-h-48 w-full rounded-lg object-cover"
					/>
					<button
						type="button"
						onclick={clearPhoto}
						aria-label="Remove photo"
						class="absolute top-2 right-2 rounded-full bg-black/50 p-1.5 text-white after:absolute after:-inset-2 after:content-[''] hover:bg-black/70"
					>
						<X class="size-3.5" />
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
				class="pointer-coarse:h-11"
				autofocus
				onkeydown={(e) => {
					if (e.key === 'Enter') void save();
				}}
			/>

			<!-- Item type -->
			<div class="space-y-1.5">
				<Label class="text-xs text-muted-foreground">Item type</Label>
				<TypePicker
					bind:value={selectedType}
					bind:creating={creatingType}
					oncreate={(type) => (types = [...types, type])}
				/>
			</div>

			<!-- Barcode -->
			{#if code === null}
				<Button
					variant="outline"
					class="w-full pointer-coarse:h-11"
					onclick={() => (scannerOpen = true)}
				>
					<ScanBarcode class="size-4" />
					Scan barcode
				</Button>
			{:else}
				<div class="space-y-2 rounded-lg border border-border p-3">
					<div class="flex items-center justify-between gap-2">
						<div class="min-w-0">
							<p class="text-xs text-muted-foreground">Barcode</p>
							<p class="truncate font-mono text-sm">{code}</p>
						</div>
						<div class="flex shrink-0 items-center gap-1">
							<Button
								variant="ghost"
								size="sm"
								class="pointer-coarse:h-11"
								onclick={() => (scannerOpen = true)}
							>
								Scan again
							</Button>
							<Button
								variant="ghost"
								size="icon-sm"
								aria-label="Remove barcode"
								class="pointer-coarse:size-11"
								onclick={() => (code = null)}
							>
								<X class="size-4" />
							</Button>
						</div>
					</div>
					{#if codeFields.length > 0}
						<div class="space-y-1.5">
							<Label for="capture-barcode-field" class="text-xs text-muted-foreground">
								Save in
							</Label>
							<NativeSelect id="capture-barcode-field" bind:value={codeField}>
								{#each codeFields as field (field.key)}
									<NativeSelectOption value={field.key}>{field.label}</NativeSelectOption>
								{/each}
								<NativeSelectOption value={NEW_BARCODE_DETAIL}
									>A new Barcode detail</NativeSelectOption
								>
							</NativeSelect>
						</div>
					{:else}
						<p class="text-xs text-muted-foreground">Saved as a Barcode detail.</p>
					{/if}
				</div>
			{/if}

			<!-- Footer -->
			<div class="flex items-center justify-between">
				<button
					type="button"
					onclick={openFullForm}
					class="text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline pointer-coarse:flex pointer-coarse:min-h-11 pointer-coarse:items-center"
				>
					Use full form →
				</button>
				<Button
					class="pointer-coarse:h-11"
					onclick={save}
					disabled={!name.trim() || saving || creatingType}
				>
					{saving ? 'Saving…' : 'Save'}
				</Button>
			</div>
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>

<BarcodeScanner bind:open={scannerOpen} onDetected={(scannedCode) => (code = scannedCode)} />
