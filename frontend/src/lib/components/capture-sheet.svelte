<script lang="ts">
	import { ScanBarcode, X } from '@lucide/svelte';
	import FileDrop from '$lib/components/file-drop.svelte';
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { captureController, type StagedPhoto } from '$lib/capture.svelte.js';
	import {
		createEdges,
		createNode,
		listEdgeTypes,
		listNodes,
		stageMedia,
		attachMedia,
		type EdgeTypeResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError, uploadErrorMessage } from '$lib/api/errors';
	import { connectionBody, connectionChoices } from '$lib/capture-connection';
	import { allowsItemType } from '$lib/connection-limits';
	import * as Combobox from '$lib/components/ui/combobox/index.js';
	import type { ComboboxItem } from '$lib/components/ui/combobox/index.js';
	import TypePicker from '$lib/components/type-picker.svelte';
	import BarcodeScanner from '$lib/components/barcode-scanner.svelte';
	import {
		NEW_BARCODE_DETAIL,
		defaultScanField,
		scanTargets,
		scannedAttributes,
		suggestScanField
	} from '$lib/barcode/scan-field';
	import { loadItemTypes } from '$lib/palette-sources';
	import { captureFieldKeys } from '$lib/quick-capture';
	import { rowsToAttributes, type AttributeRow } from '$lib/attribute-rows';
	import AttributesEditor from '$lib/components/attributes-editor.svelte';
	import { effectiveSchema } from '$lib/node-types';
	import { mergeAttributeSchemas } from '$lib/schema-meta';
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
	let rows = $state<AttributeRow[]>([]);
	let edgeTypes = $state<EdgeTypeResponse[]>([]);
	let connectionKey = $state('');
	let connectTo = $state<{ id: string; name: string } | null>(null);
	let found = $state<{ id: string; name: string; type: string | null }[]>([]);
	let searchTimer: ReturnType<typeof setTimeout> | undefined;
	let searchSeq = 0;

	// Only the readings the new item's type allows, and only items the other end allows.
	const choices = $derived(connectionChoices(edgeTypes, selectedType));
	const choice = $derived(choices.find((c) => c.key === connectionKey) ?? null);
	const targetItems = $derived.by((): ComboboxItem[] => {
		const out: ComboboxItem[] = connectTo ? [{ value: connectTo.id, label: connectTo.name }] : [];
		for (const item of found)
			if (item.id !== connectTo?.id && allowsItemType(choice?.pickedTypes, item.type))
				out.push({ value: item.id, label: item.name });
		return out;
	});

	// Connection types are read when the sheet opens, and the last connection made is offered again.
	$effect(() => {
		if (!captureController.open) return;
		void listEdgeTypes({ query: { limit: 100 } }).then((r) => {
			edgeTypes = r.data ?? [];
			const last = captureController.lastConnection;
			if (last && connectionChoices(edgeTypes).some((c) => c.key === last.key)) {
				connectionKey = last.key;
				connectTo = last.target;
			}
		});
	});

	// Changing the connection can leave the picked item outside what its other end allows.
	$effect(() => {
		const picked = connectTo ? found.find((n) => n.id === connectTo?.id) : undefined;
		if (picked && !allowsItemType(choice?.pickedTypes, picked.type)) connectTo = null;
	});

	function searchTargets(text: string) {
		clearTimeout(searchTimer);
		const mine = ++searchSeq;
		searchTimer = setTimeout(
			async () => {
				// One allowed type is asked of the server, so a full page of others cannot hide it.
				const allowed = choice?.pickedTypes ?? [];
				const r = await listNodes({
					query: {
						limit: 20,
						q: text || undefined,
						type: allowed.length === 1 ? allowed[0] : undefined
					}
				});
				if (mine === searchSeq && r.data)
					found = r.data.map((n) => ({ id: n.id, name: n.name, type: n.type ?? null }));
			},
			text ? 250 : 0
		);
	}

	function pickTarget(id: string) {
		const item = [...found, ...(connectTo ? [connectTo] : [])].find((n) => n.id === id);
		if (item) connectTo = item;
	}

	// Types are read once a type is chosen or a code is scanned, to offer the type's fields.
	$effect(() => {
		if (selectedType !== null || code !== null)
			void loadItemTypes()
				.then((all) => (types = all))
				.catch(() => {});
	});

	const typeSchema = $derived(effectiveSchema(types.find((type) => type.slug === selectedType)));
	const captureKeys = $derived(captureFieldKeys(typeSchema));
	// A field marked as taking barcodes, else one whose label looks like a code.
	const defaultCodeField = $derived(defaultScanField(typeSchema));
	// When that field is shown here, the code goes into it, in view.
	const shownCodeField = $derived(
		defaultCodeField !== null && captureKeys.includes(defaultCodeField) ? defaultCodeField : null
	);
	// Otherwise the person picks a field that isn't shown, or a new detail.
	const codeFields = $derived(
		scanTargets(typeSchema).filter((field) => !captureKeys.includes(field.key))
	);

	// Values typed for one type don't belong to another.
	$effect.pre(() => {
		void selectedType;
		rows = [];
	});

	$effect(() => {
		if (code === null || shownCodeField === null) return;
		const key = shownCodeField;
		rows = [...rows.filter((row) => row.key !== key), { key, value: code }];
		code = null;
	});

	/** The fields filled in as form rows, with a scanned code in its field (or a new detail). */
	function details() {
		const barcode = scanned();
		const codeRows = Object.entries(barcode?.attributes ?? {}).map(([key, value]) => ({
			key,
			value
		}));
		const kept = $state
			.snapshot(rows)
			.filter((row) => !codeRows.some((code) => code.key === row.key));
		const handed = [...kept, ...codeRows];
		if (handed.length === 0) return null;
		return { rows: handed, extraSchema: barcode?.extraSchema ?? null };
	}

	// Follows the type until the person picks a field themselves.
	let codeField = $derived(
		codeFields.some((field) => field.key === defaultCodeField)
			? defaultCodeField!
			: (suggestScanField(codeFields) ?? NEW_BARCODE_DETAIL)
	);

	function scanned() {
		return code === null ? null : scannedAttributes(code, codeField, typeSchema);
	}

	async function handlePhotoChange(files: FileList | File[]) {
		const file = Array.from(files)[0] ?? null;
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
		const filled = details();
		const attributes =
			filled &&
			rowsToAttributes(filled.rows, mergeAttributeSchemas(typeSchema, filled.extraSchema));
		const result = await createNode({
			body: {
				name: name.trim(),
				type: selectedType || null,
				...(filled &&
					attributes &&
					Object.keys(attributes).length > 0 && {
						attributes,
						extra_schema: filled.extraSchema
					})
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
		if (choice && connectTo) {
			// The item is already saved; a failed connection leaves it there and says so.
			const linked = await createEdges({
				body: connectionBody(choice, result.data.id, connectTo.id)
			});
			if (linked.error || !linked.data) {
				const { title, description } = linked.response
					? { title: "Saved, but couldn't connect it", description: errorMessage(linked.error) }
					: networkAwareError(linked);
				toast.error(title, { description });
			} else {
				captureController.lastConnection = { key: choice.key, target: connectTo };
			}
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
			details: details()
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
		rows = [];
		connectionKey = '';
		connectTo = null;
		found = [];
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
				<FileDrop
					onFiles={handlePhotoChange}
					multiple={false}
					accept="image/*"
					label={staging ? 'Adding…' : 'Add photo'}
					camera
					disabled={staging}
				/>
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

			{#if captureKeys.length > 0}
				<AttributesEditor bind:rows schema={typeSchema} only={captureKeys} />
			{/if}

			<!-- Connect to -->
			{#if choices.length > 0}
				<div class="space-y-1.5">
					<Label for="capture-connection" class="text-xs text-muted-foreground">Connect to</Label>
					<NativeSelect id="capture-connection" bind:value={connectionKey}>
						<NativeSelectOption value="">Nothing</NativeSelectOption>
						{#each choices as option (option.key)}
							<NativeSelectOption value={option.key}>{option.label}…</NativeSelectOption>
						{/each}
					</NativeSelect>
					{#if choice}
						<Combobox.Root
							aria-label="{choice.label} which item"
							items={targetItems}
							value={connectTo?.id ?? ''}
							placeholder="Choose an item"
							searchPlaceholder="Search items…"
							emptyText="No matching items"
							onsearch={searchTargets}
							onValueChange={pickTarget}
						/>
					{/if}
				</div>
			{/if}

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
								<NativeSelectOption value={NEW_BARCODE_DETAIL}>
									A new Barcode detail
								</NativeSelectOption>
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
