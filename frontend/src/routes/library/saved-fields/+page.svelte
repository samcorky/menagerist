<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import { resolve } from '$app/paths';
	import {
		Bookmark,
		ChevronDown,
		Copy,
		Download,
		Layers,
		ListChecks,
		Pencil,
		Trash2,
		Upload,
		MoreVertical,
		Library
	} from '@lucide/svelte';
	import ListRowSkeleton from '$lib/components/list-row-skeleton.svelte';
	import PageNav from '$lib/components/page-nav.svelte';
	import { PagedList } from '$lib/paged-list.svelte';
	import { untrack } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';
	import {
		createPreset,
		deletePreset,
		importBundle,
		planBundleImport,
		listPresets,
		type PresetResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import PlanPreviewDialog from '$lib/components/plan-preview-dialog.svelte';
	import type { ImportPlan } from '$lib/import-plan';
	import CatalogueDialog from '$lib/components/catalogue-dialog.svelte';
	import CollapsibleSection from '$lib/components/collapsible-section.svelte';
	import IconButton from '$lib/components/icon-button.svelte';
	import LoadFailed from '$lib/components/load-failed.svelte';
	import { offlineController } from '$lib/offline.svelte.js';
	import BackButton from '$lib/components/back-button.svelte';
	import EditListDialog from '$lib/components/edit-list-dialog.svelte';
	import PresetExample from '$lib/components/preset-example.svelte';
	import {
		canEditOptions,
		downloadBundle,
		exportPresetBundle,
		fetchAllPresets,
		kindNoun,
		bundleKindMismatch,
		parseBundleText,
		presetFilename,
		type PackSectionKind,
		type PresetBundle
	} from '$lib/preset-packs';

	// Three lists share this screen, so each pages, ten at a time.
	const PAGE_SIZE = 10;
	const sectionFilenames: Record<PackSectionKind, string> = {
		field: 'menagerist-fields.json',
		choice_list: 'menagerist-lists.json',
		field_set: 'menagerist-field-groups.json'
	};

	// Newest first, so a copy made here is at the top of its first page.
	const presetList = (kind: PackSectionKind) =>
		new PagedList<PresetResponse, null>(
			({ after }) =>
				listPresets({
					query: { kind, after, limit: PAGE_SIZE, sort: ['created_at'], order: ['desc'] }
				}),
			{ mode: 'page' }
		);
	const fieldsList = presetList('field');
	const listsList = presetList('choice_list');
	const fieldSetsList = presetList('field_set');
	const fields = $derived(fieldsList.rows);
	const lists = $derived(listsList.rows);
	const fieldSets = $derived(fieldSetsList.rows);
	const fieldsLoading = $derived(fieldsList.loading);
	const listsLoading = $derived(listsList.loading);
	const fieldSetsLoading = $derived(fieldSetsList.loading);
	const fieldsLoadFailed = $derived(fieldsList.failed);
	const listsLoadFailed = $derived(listsList.failed);
	const fieldSetsLoadFailed = $derived(fieldSetsList.failed);

	function handleDelete(preset: PresetResponse, collection: 'fields' | 'lists' | 'fieldSets') {
		const list =
			collection === 'fields' ? fieldsList : collection === 'lists' ? listsList : fieldSetsList;

		// No items ever depend on a preset the way categories depend on connections - always
		// use the optimistic undo path.
		list.rows = list.rows.filter((p) => p.id !== preset.id);

		let undone = false;
		const timerId = setTimeout(async () => {
			if (undone) return;
			const result = await deletePreset({ path: { preset_id: preset.id } });
			if (result.error) {
				list.rows = [preset, ...list.rows];
				toast.error("Couldn't delete", { description: errorMessage(result.error) });
			} else {
				// Read the page again, so it fills up and the counts are right.
				void list.refresh();
			}
		}, 5000);

		toast(
			collection === 'fields'
				? 'Field deleted'
				: collection === 'lists'
					? 'List deleted'
					: 'Field group deleted',
			{
				action: {
					label: 'Undo',
					onClick: () => {
						undone = true;
						clearTimeout(timerId);
						list.rows = [preset, ...list.rows];
					}
				},
				duration: 5000
			}
		);
	}

	function listOptionCount(preset: PresetResponse): number | undefined {
		const options = (preset.definition as { options?: unknown }).options;
		return Array.isArray(options) ? options.length : undefined;
	}

	function fieldSetPropertyCount(preset: PresetResponse): number | undefined {
		const properties = (preset.definition as { properties?: unknown }).properties;
		return Array.isArray(properties) ? properties.length : undefined;
	}

	let busy = $state(false);
	let sectionBusy = $state(false);
	let importInput = $state<HTMLInputElement | null>(null);
	let sectionImportInputs = $state<Record<PackSectionKind, HTMLInputElement | null>>({
		field: null,
		choice_list: null,
		field_set: null
	});
	let editOpen = $state(false);
	let editingList = $state<PresetResponse | null>(null);
	let editSession = $state(0);
	let copying = $state(false);

	function failureMessage(error: unknown): string {
		return error instanceof Error ? error.message : errorMessage(error);
	}

	let catalogueOpen = $state(false);

	async function reloadAll() {
		await Promise.all([fieldsList.load(null), listsList.load(null), fieldSetsList.load(null)]);
	}

	// The file chosen to import, and what importing it would do, until it is confirmed.
	let pendingImport = $state<{ bundle: PresetBundle; kind?: PackSectionKind } | null>(null);
	let plan = $state<ImportPlan | null>(null);
	let planLoading = $state(false);
	let planError = $state<string | null>(null);

	async function previewImport(event: Event, kind?: PackSectionKind) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;

		try {
			const bundle = parseBundleText(await file.text());
			const mismatch = kind ? bundleKindMismatch(bundle, kind) : null;
			if (mismatch) {
				toast.error("Can't import here", { description: mismatch });
				return;
			}
			pendingImport = { bundle, kind };
			plan = null;
			planError = null;
			planLoading = true;
			const result = await planBundleImport({ body: bundle });
			planLoading = false;
			if (result.error || !result.data) {
				planError = errorMessage(result.error);
				return;
			}
			plan = result.data;
		} catch (error) {
			toast.error("Couldn't import", { description: failureMessage(error) });
		} finally {
			input.value = '';
		}
	}

	function closeImportPreview(open: boolean) {
		if (!open && !busy && !sectionBusy) pendingImport = null;
	}

	async function confirmImport() {
		const pending = pendingImport;
		if (!pending) return;
		const { bundle, kind } = pending;

		if (kind) sectionBusy = true;
		else busy = true;
		try {
			const result = await importBundle({ body: bundle });
			pendingImport = null;
			if (result.error || !result.data) {
				toast.error("Couldn't import", { description: errorMessage(result.error) });
				return;
			}
			const { created, skipped } = result.data;
			const skippedText =
				skipped > 0
					? `${skipped} ${skipped === 1 ? 'was' : 'were'} already saved and skipped`
					: undefined;
			if (created === 0) {
				toast('Nothing new to import', { description: skippedText });
			} else {
				const noun = kind ? kindNoun(kind, created) : created === 1 ? 'preset' : 'presets';
				toast.success(`Imported ${created} ${noun}`, { description: skippedText });
			}
			await reloadAll();
		} catch (error) {
			pendingImport = null;
			toast.error("Couldn't import", { description: failureMessage(error) });
		} finally {
			busy = false;
			sectionBusy = false;
		}
	}

	function handleImportFile(event: Event) {
		return previewImport(event);
	}

	async function handleExport() {
		busy = true;
		try {
			const all = await fetchAllPresets();
			downloadBundle(await exportPresetBundle(all));
		} catch (error) {
			toast.error("Couldn't export", { description: failureMessage(error) });
		} finally {
			busy = false;
		}
	}

	async function handleSectionExport(kind: PackSectionKind) {
		if (sectionBusy) return;
		sectionBusy = true;
		try {
			const presets = (await fetchAllPresets()).filter((p) => p.kind === kind);
			if (presets.length === 0) {
				toast('Nothing to export');
				return;
			}
			downloadBundle(await exportPresetBundle(presets), sectionFilenames[kind]);
		} catch (error) {
			toast.error("Couldn't export", { description: failureMessage(error) });
		} finally {
			sectionBusy = false;
		}
	}

	function handleSectionImport(kind: PackSectionKind, event: Event) {
		return previewImport(event, kind);
	}

	async function handlePresetExport(preset: PresetResponse) {
		if (sectionBusy) return;
		sectionBusy = true;
		try {
			downloadBundle(await exportPresetBundle([preset]), presetFilename(preset.label));
		} catch (error) {
			toast.error("Couldn't export", { description: failureMessage(error) });
		} finally {
			sectionBusy = false;
		}
	}

	async function copyPreset(preset: PresetResponse) {
		if (copying) return;
		copying = true;
		try {
			const result = await createPreset({
				body: {
					kind: preset.kind,
					label: `${preset.label} (copy)`,
					description: preset.description ?? null,
					definition: preset.definition
				}
			});
			if (result.error || !result.data) {
				toast.error("Couldn't copy", { description: errorMessage(result.error) });
				return;
			}
			const copy = result.data;
			// Newest first, so the copy is at the top of the first page.
			if (copy.kind === 'field') void fieldsList.load(null, { keepRows: true });
			else if (copy.kind === 'choice_list') void listsList.load(null, { keepRows: true });
			else if (copy.kind === 'field_set') void fieldSetsList.load(null, { keepRows: true });
			toast.success('Copied');
		} finally {
			copying = false;
		}
	}

	const openExamples = new SvelteSet<string>();

	function toggleExample(id: string) {
		if (openExamples.has(id)) openExamples.delete(id);
		else openExamples.add(id);
	}

	function openEdit(preset: PresetResponse) {
		editingList = preset;
		editSession += 1;
		editOpen = true;
	}

	function handleListSaved(saved: PresetResponse) {
		listsList.rows = listsList.rows.map((p) => (p.id === saved.id ? saved : p));
	}

	$effect(() => {
		void fieldsList.load(null, { keepRows: true });
	});

	$effect(() => {
		void listsList.load(null, { keepRows: true });
	});

	$effect(() => {
		void fieldSetsList.load(null, { keepRows: true });
	});

	// Coming back online, or Retry in the banner, reloads any section that had failed.
	$effect(() => {
		void offlineController.retryCount;
		untrack(() => {
			if (fieldsLoadFailed) void fieldsList.retry();
			if (listsLoadFailed) void listsList.retry();
			if (fieldSetsLoadFailed) void fieldSetsList.retry();
		});
	});
</script>

<svelte:head>
	<title>Saved fields - Menagerist</title>
</svelte:head>

{#snippet sectionActions(title: string, kind: PackSectionKind)}
	<div class="flex items-center gap-1">
		<input
			bind:this={sectionImportInputs[kind]}
			type="file"
			accept="application/json,.json"
			class="hidden"
			onchange={(event) => handleSectionImport(kind, event)}
		/>
		<IconButton
			labelOnTouch={false}
			label={`Import ${title.toLowerCase()}`}
			disabled={sectionBusy}
			onclick={() => sectionImportInputs[kind]?.click()}
		>
			<Upload />
		</IconButton>
		<IconButton
			labelOnTouch={false}
			label={`Export ${title.toLowerCase()}`}
			disabled={sectionBusy}
			onclick={() => handleSectionExport(kind)}
		>
			<Download />
		</IconButton>
	</div>
{/snippet}

{#snippet presetRow(
	preset: PresetResponse,
	deleteKey: 'fields' | 'lists' | 'fieldSets',
	deleteLabel: string,
	meta?: string
)}
	<li class="px-3 py-2">
		<div class="flex items-center gap-1">
			<div class="min-w-0 flex-1">
				<div class="flex flex-wrap items-center gap-2">
					<span class="truncate font-medium">{preset.label}</span>
					{#if meta}
						<span class="text-xs text-muted-foreground">{meta}</span>
					{/if}
				</div>
				{#if preset.description}
					<p class="truncate text-sm text-muted-foreground">{preset.description}</p>
				{/if}
			</div>
			<IconButton
				labelOnTouch={false}
				label="Try it"
				aria-expanded={openExamples.has(preset.id)}
				aria-controls="example-{preset.id}"
				onclick={() => toggleExample(preset.id)}
			>
				<ChevronDown
					class="transition-transform duration-150 {openExamples.has(preset.id)
						? 'rotate-180'
						: ''}"
				/>
			</IconButton>
			{#if canEditOptions(preset)}
				<IconButton
					labelOnTouch={false}
					label="Edit {preset.label}"
					onclick={() => openEdit(preset)}
				>
					<Pencil />
				</IconButton>
			{/if}
			<DropdownMenu.Root>
				<DropdownMenu.Trigger>
					{#snippet child({ props })}
						<Button
							{...props}
							type="button"
							variant="ghost"
							size="icon"
							class="pointer-coarse:size-11"
							aria-label="More actions for {preset.label}"
						>
							<MoreVertical class="size-4" />
						</Button>
					{/snippet}
				</DropdownMenu.Trigger>
				<DropdownMenu.Content align="end">
					<DropdownMenu.Item
						class="pointer-coarse:min-h-11"
						disabled={sectionBusy}
						onSelect={() => handlePresetExport(preset)}
					>
						<Download class="size-4" />
						Export
					</DropdownMenu.Item>
					<DropdownMenu.Item
						class="pointer-coarse:min-h-11"
						disabled={copying}
						onSelect={() => copyPreset(preset)}
					>
						<Copy class="size-4" />
						Copy
					</DropdownMenu.Item>
				</DropdownMenu.Content>
			</DropdownMenu.Root>
			<IconButton
				labelOnTouch={false}
				label={deleteLabel}
				onclick={() => handleDelete(preset, deleteKey)}
			>
				<Trash2 />
			</IconButton>
		</div>
		{#if openExamples.has(preset.id)}
			<div id="example-{preset.id}" class="pt-2">
				<PresetExample {preset} />
			</div>
		{/if}
	</li>
{/snippet}

<Page width="reading" class="gap-6">
	<BackButton peer fallback={resolve('/settings')} />

	<div class="flex flex-wrap items-start justify-between gap-4">
		<div class="min-w-0 flex-1 basis-64">
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Saved fields</h1>
			<p class="mt-1 text-muted-foreground">
				Reuse a field or a list of choices across item types instead of rebuilding it each time.
			</p>
		</div>
		<input
			bind:this={importInput}
			type="file"
			accept="application/json,.json"
			class="hidden"
			onchange={handleImportFile}
		/>
		<div class="flex shrink-0 items-center gap-2">
			<Button
				type="button"
				variant="outline"
				class="pointer-coarse:min-h-11"
				onclick={() => (catalogueOpen = true)}
			>
				<Library class="size-4" />
				Install from catalogue
			</Button>
			<DropdownMenu.Root>
				<DropdownMenu.Trigger>
					{#snippet child({ props })}
						<Button
							{...props}
							type="button"
							variant="outline"
							size="icon"
							class="pointer-coarse:size-11"
							aria-label="More actions"
						>
							<MoreVertical class="size-4" />
						</Button>
					{/snippet}
				</DropdownMenu.Trigger>
				<DropdownMenu.Content align="end" class="min-w-52">
					<DropdownMenu.Item
						class="pointer-coarse:min-h-11"
						disabled={busy}
						onSelect={() => importInput?.click()}
					>
						<Upload class="size-4" />
						Import
					</DropdownMenu.Item>
					<DropdownMenu.Item
						class="pointer-coarse:min-h-11"
						disabled={busy}
						onSelect={handleExport}
					>
						<Download class="size-4" />
						Export all
					</DropdownMenu.Item>
				</DropdownMenu.Content>
			</DropdownMenu.Root>
		</div>
	</div>

	<CollapsibleSection
		id="saved-fields-fields"
		title="Fields"
		count={fieldsList.count ?? undefined}
		class="gap-3"
	>
		{#snippet actions()}
			{@render sectionActions('Fields', 'field')}
		{/snippet}

		{#if fieldsLoading && fields.length === 0}
			<ListRowSkeleton count={3} />
		{:else if fieldsLoadFailed}
			<LoadFailed what="your saved fields" onretry={() => void fieldsList.retry()} />
		{:else}
			<ul class="divide-y rounded-xl border bg-card">
				{#each fields as preset (preset.id)}
					{@render presetRow(preset, 'fields', 'Delete field')}
				{/each}
			</ul>

			{#if fields.length === 0 && !fieldsLoading}
				<div class="flex flex-col items-center gap-3 py-10 text-center">
					<Bookmark class="size-10 text-muted-foreground/50" />
					<p class="font-medium">No saved fields yet</p>
				</div>
			{/if}
		{/if}

		<PageNav list={fieldsList} noun="saved field" />
	</CollapsibleSection>

	<CollapsibleSection
		id="saved-fields-lists"
		title="Lists"
		count={listsList.count ?? undefined}
		class="gap-3"
	>
		{#snippet actions()}
			{@render sectionActions('Lists', 'choice_list')}
		{/snippet}

		{#if listsLoading && lists.length === 0}
			<ListRowSkeleton count={3} />
		{:else if listsLoadFailed}
			<LoadFailed what="your saved lists" onretry={() => void listsList.retry()} />
		{:else}
			<ul class="divide-y rounded-xl border bg-card">
				{#each lists as preset (preset.id)}
					{@const optionCount = listOptionCount(preset)}
					{@render presetRow(
						preset,
						'lists',
						'Delete list',
						optionCount === undefined
							? undefined
							: optionCount === 1
								? '1 option'
								: `${optionCount} options`
					)}
				{/each}
			</ul>

			{#if lists.length === 0 && !listsLoading}
				<div class="flex flex-col items-center gap-3 py-10 text-center">
					<ListChecks class="size-10 text-muted-foreground/50" />
					<p class="font-medium">No saved lists yet</p>
				</div>
			{/if}
		{/if}

		<PageNav list={listsList} noun="saved list" />
	</CollapsibleSection>

	<CollapsibleSection
		id="saved-fields-field-groups"
		title="Field groups"
		count={fieldSetsList.count ?? undefined}
		class="gap-3"
	>
		{#snippet actions()}
			{@render sectionActions('Field groups', 'field_set')}
		{/snippet}

		{#if fieldSetsLoading && fieldSets.length === 0}
			<ListRowSkeleton count={3} />
		{:else if fieldSetsLoadFailed}
			<LoadFailed what="your saved field groups" onretry={() => void fieldSetsList.retry()} />
		{:else}
			<ul class="divide-y rounded-xl border bg-card">
				{#each fieldSets as preset (preset.id)}
					{@const propertyCount = fieldSetPropertyCount(preset)}
					{@render presetRow(
						preset,
						'fieldSets',
						'Delete field group',
						propertyCount === undefined
							? undefined
							: propertyCount === 1
								? '1 field'
								: `${propertyCount} fields`
					)}
				{/each}
			</ul>

			{#if fieldSets.length === 0 && !fieldSetsLoading}
				<div class="flex flex-col items-center gap-3 py-10 text-center">
					<Layers class="size-10 text-muted-foreground/50" />
					<p class="font-medium">No saved field groups yet</p>
				</div>
			{/if}
		{/if}

		<PageNav list={fieldSetsList} noun="field group" />
	</CollapsibleSection>
	{#if editingList}
		{#key editSession}
			<EditListDialog
				preset={editingList}
				open={editOpen}
				onOpenChange={(value: boolean) => (editOpen = value)}
				onsaved={handleListSaved}
			/>
		{/key}
	{/if}
</Page>

<PlanPreviewDialog
	open={pendingImport !== null}
	title="Import saved items"
	description="Here is what this file would add."
	{plan}
	loading={planLoading}
	error={planError}
	busy={busy || sectionBusy}
	confirmLabel="Import"
	busyLabel="Importing…"
	onOpenChange={closeImportPreview}
	onConfirm={() => void confirmImport()}
/>

<CatalogueDialog
	open={catalogueOpen}
	onOpenChange={(value) => (catalogueOpen = value)}
	onInstalled={() => void reloadAll()}
/>
