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
		Ellipsis
	} from '@lucide/svelte';
	import { Shimmer } from '@shimmer-from-structure/svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';
	import {
		createPreset,
		deletePreset,
		importPresets,
		listPresets,
		type PresetResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import CollapsibleSection from '$lib/components/collapsible-section.svelte';
	import IconButton from '$lib/components/icon-button.svelte';
	import BackButton from '$lib/components/back-button.svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import EditListDialog from '$lib/components/edit-list-dialog.svelte';
	import PresetExample from '$lib/components/preset-example.svelte';
	import {
		canEditOptions,
		copyLabel,
		downloadPack,
		exportPack,
		fetchAllPresets,
		kindNoun,
		packKindMismatch,
		parsePackText,
		presetFilename,
		readShowBuiltins,
		visiblePresets,
		writeShowBuiltins,
		type PackSectionKind
	} from '$lib/preset-packs';

	const PAGE_SIZE = 50;
	const loadingSkeletons = [1, 2, 3];
	const sectionFilenames: Record<PackSectionKind, string> = {
		field: 'menagerist-fields.json',
		choice_list: 'menagerist-lists.json',
		field_set: 'menagerist-field-groups.json'
	};

	let fields = $state<PresetResponse[]>([]);
	let fieldsLoading = $state(false);
	let fieldsHasMore = $state(true);

	let lists = $state<PresetResponse[]>([]);
	let listsLoading = $state(false);
	let listsHasMore = $state(true);

	let fieldSets = $state<PresetResponse[]>([]);
	let fieldSetsLoading = $state(false);
	let fieldSetsHasMore = $state(true);

	let showBuiltins = $state(readShowBuiltins());
	const visibleFields = $derived(visiblePresets(fields, showBuiltins));
	const visibleLists = $derived(visiblePresets(lists, showBuiltins));
	const visibleFieldSets = $derived(visiblePresets(fieldSets, showBuiltins));

	function setShowBuiltins(show: boolean) {
		showBuiltins = show;
		writeShowBuiltins(show);
	}

	async function fetchFields(after?: string) {
		fieldsLoading = true;
		const result = await listPresets({ query: { kind: 'field', after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			toast.error("Couldn't load saved fields", { description: errorMessage(result.error) });
		} else {
			fields = after ? [...fields, ...result.data] : result.data;
			fieldsHasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		fieldsLoading = false;
	}

	async function fetchLists(after?: string) {
		listsLoading = true;
		const result = await listPresets({ query: { kind: 'choice_list', after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			toast.error("Couldn't load saved lists", { description: errorMessage(result.error) });
		} else {
			lists = after ? [...lists, ...result.data] : result.data;
			listsHasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		listsLoading = false;
	}

	async function fetchFieldSets(after?: string) {
		fieldSetsLoading = true;
		const result = await listPresets({ query: { kind: 'field_set', after, limit: PAGE_SIZE } });
		if (result.error || !result.data) {
			toast.error("Couldn't load saved field groups", { description: errorMessage(result.error) });
		} else {
			fieldSets = after ? [...fieldSets, ...result.data] : result.data;
			fieldSetsHasMore = /rel="next"/.test(result.response?.headers.get('link') ?? '');
		}
		fieldSetsLoading = false;
	}

	function fieldsSentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && fieldsHasMore && !fieldsLoading)
					void fetchFields(fields.at(-1)?.id);
			},
			{ rootMargin: '200px' }
		);
		observer.observe(node);
		return {
			destroy() {
				observer.disconnect();
			}
		};
	}

	function listsSentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && listsHasMore && !listsLoading)
					void fetchLists(lists.at(-1)?.id);
			},
			{ rootMargin: '200px' }
		);
		observer.observe(node);
		return {
			destroy() {
				observer.disconnect();
			}
		};
	}

	function handleDelete(preset: PresetResponse, collection: 'fields' | 'lists' | 'fieldSets') {
		const setItems =
			collection === 'fields'
				? (v: PresetResponse[]) => (fields = v)
				: collection === 'lists'
					? (v: PresetResponse[]) => (lists = v)
					: (v: PresetResponse[]) => (fieldSets = v);
		const current = collection === 'fields' ? fields : collection === 'lists' ? lists : fieldSets;

		// No items ever depend on a preset the way categories depend on connections - always
		// use the optimistic undo path.
		setItems(current.filter((p) => p.id !== preset.id));

		let undone = false;
		const timerId = setTimeout(async () => {
			if (undone) return;
			const result = await deletePreset({ path: { preset_id: preset.id } });
			if (result.error) {
				const restored =
					collection === 'fields' ? fields : collection === 'lists' ? lists : fieldSets;
				setItems([preset, ...restored]);
				toast.error("Couldn't delete", { description: errorMessage(result.error) });
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
						const restored =
							collection === 'fields' ? fields : collection === 'lists' ? lists : fieldSets;
						setItems([preset, ...restored]);
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

	function fieldSetsSentinel(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && fieldSetsHasMore && !fieldSetsLoading)
					void fetchFieldSets(fieldSets.at(-1)?.id);
			},
			{ rootMargin: '200px' }
		);
		observer.observe(node);
		return {
			destroy() {
				observer.disconnect();
			}
		};
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

	async function reloadAll() {
		fields = [];
		lists = [];
		fieldSets = [];
		fieldsHasMore = true;
		listsHasMore = true;
		fieldSetsHasMore = true;
		await Promise.all([fetchFields(), fetchLists(), fetchFieldSets()]);
	}

	async function handleImportFile(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;

		busy = true;
		try {
			const pack = parsePackText(await file.text());
			const result = await importPresets({
				body: { format: pack.format, version: pack.version, items: pack.items }
			});
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
				toast.success(`Imported ${created} ${created === 1 ? 'preset' : 'presets'}`, {
					description: skippedText
				});
			}
			await reloadAll();
		} catch (error) {
			toast.error("Couldn't import", { description: failureMessage(error) });
		} finally {
			input.value = '';
			busy = false;
		}
	}

	async function handleExport() {
		busy = true;
		try {
			const all = await fetchAllPresets();
			downloadPack(await exportPack(all));
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
			const presets = visiblePresets(
				(await fetchAllPresets()).filter((p) => p.kind === kind),
				showBuiltins
			);
			if (presets.length === 0) {
				toast('Nothing to export');
				return;
			}
			downloadPack(await exportPack(presets), sectionFilenames[kind]);
		} catch (error) {
			toast.error("Couldn't export", { description: failureMessage(error) });
		} finally {
			sectionBusy = false;
		}
	}

	async function handleSectionImport(kind: PackSectionKind, event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;

		sectionBusy = true;
		try {
			const pack = parsePackText(await file.text());
			const mismatch = packKindMismatch(pack, kind);
			if (mismatch) {
				toast.error("Can't import here", { description: mismatch });
				return;
			}
			const result = await importPresets({
				body: { format: pack.format, version: pack.version, items: pack.items }
			});
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
				toast.success(`Imported ${created} ${kindNoun(kind, created)}`, {
					description: skippedText
				});
			}
			await reloadAll();
		} catch (error) {
			toast.error("Couldn't import", { description: failureMessage(error) });
		} finally {
			input.value = '';
			sectionBusy = false;
		}
	}

	async function handlePresetExport(preset: PresetResponse) {
		if (sectionBusy) return;
		sectionBusy = true;
		try {
			downloadPack(await exportPack([preset]), presetFilename(preset.label));
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
					label: copyLabel(preset.label),
					description: preset.description ?? null,
					definition: preset.definition
				}
			});
			if (result.error || !result.data) {
				toast.error("Couldn't copy", { description: errorMessage(result.error) });
				return;
			}
			const copy = result.data;
			if (copy.kind === 'field') fields = [copy, ...fields];
			else if (copy.kind === 'choice_list') lists = [copy, ...lists];
			else if (copy.kind === 'field_set') fieldSets = [copy, ...fieldSets];
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
		lists = lists.map((p) => (p.id === saved.id ? saved : p));
	}

	$effect(() => {
		void fetchFields();
	});

	$effect(() => {
		void fetchLists();
	});

	$effect(() => {
		void fetchFieldSets();
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
					{#if preset.builtin}
						<Badge variant="secondary">Built-in</Badge>
					{/if}
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
							<Ellipsis class="size-4" />
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
				disabled={preset.builtin}
				title={preset.builtin ? "Built-in items can't be deleted" : undefined}
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
	<BackButton fallback={resolve('/settings')} />

	<div class="flex items-start justify-between gap-4">
		<div>
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
						<Ellipsis class="size-4" />
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
				<DropdownMenu.Item class="pointer-coarse:min-h-11" disabled={busy} onSelect={handleExport}>
					<Download class="size-4" />
					Export all
				</DropdownMenu.Item>
				<DropdownMenu.Separator />
				<DropdownMenu.CheckboxItem
					class="pointer-coarse:min-h-11"
					checked={showBuiltins}
					onCheckedChange={(value) => setShowBuiltins(value)}
				>
					Show built-in fields, lists and groups
				</DropdownMenu.CheckboxItem>
			</DropdownMenu.Content>
		</DropdownMenu.Root>
	</div>

	<CollapsibleSection
		id="saved-fields-fields"
		title="Fields"
		count={visibleFields.length}
		class="gap-3"
	>
		{#snippet actions()}
			{@render sectionActions('Fields', 'field')}
		{/snippet}

		{#if fieldsLoading && fields.length === 0}
			<Shimmer loading={true}>
				<div class="grid gap-3">
					{#each loadingSkeletons as s (s)}
						<div class="rounded-lg border p-4">
							<div class="space-y-1">
								<div class="h-5 w-48 rounded bg-muted"></div>
								<div class="h-4 w-32 rounded-full bg-muted"></div>
							</div>
						</div>
					{/each}
				</div>
			</Shimmer>
		{:else}
			<ul class="divide-y rounded-xl border bg-card">
				{#each visibleFields as preset (preset.id)}
					{@render presetRow(preset, 'fields', 'Delete field')}
				{/each}
			</ul>

			{#if visibleFields.length === 0 && !fieldsLoading}
				<div class="flex flex-col items-center gap-3 py-10 text-center">
					<Bookmark class="size-10 text-muted-foreground/50" />
					{#if fields.length > 0}
						<p class="text-sm text-muted-foreground">Built-in items are hidden</p>
					{:else}
						<p class="font-medium">No saved fields yet</p>
					{/if}
				</div>
			{/if}
		{/if}

		{#if fieldsHasMore}
			<div use:fieldsSentinel class="flex justify-center py-2" aria-hidden="true">
				{#if fieldsLoading}
					<div
						class="size-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground"
					></div>
				{/if}
			</div>
		{/if}
	</CollapsibleSection>

	<CollapsibleSection
		id="saved-fields-lists"
		title="Lists"
		count={visibleLists.length}
		class="gap-3"
	>
		{#snippet actions()}
			{@render sectionActions('Lists', 'choice_list')}
		{/snippet}

		{#if listsLoading && lists.length === 0}
			<Shimmer loading={true}>
				<div class="grid gap-3">
					{#each loadingSkeletons as s (s)}
						<div class="rounded-lg border p-4">
							<div class="space-y-1">
								<div class="h-5 w-48 rounded bg-muted"></div>
								<div class="h-4 w-32 rounded-full bg-muted"></div>
							</div>
						</div>
					{/each}
				</div>
			</Shimmer>
		{:else}
			<ul class="divide-y rounded-xl border bg-card">
				{#each visibleLists as preset (preset.id)}
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

			{#if visibleLists.length === 0 && !listsLoading}
				<div class="flex flex-col items-center gap-3 py-10 text-center">
					<ListChecks class="size-10 text-muted-foreground/50" />
					{#if lists.length > 0}
						<p class="text-sm text-muted-foreground">Built-in items are hidden</p>
					{:else}
						<p class="font-medium">No saved lists yet</p>
					{/if}
				</div>
			{/if}
		{/if}

		{#if listsHasMore}
			<div use:listsSentinel class="flex justify-center py-2" aria-hidden="true">
				{#if listsLoading}
					<div
						class="size-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground"
					></div>
				{/if}
			</div>
		{/if}
	</CollapsibleSection>

	<CollapsibleSection
		id="saved-fields-field-groups"
		title="Field groups"
		count={visibleFieldSets.length}
		class="gap-3"
	>
		{#snippet actions()}
			{@render sectionActions('Field groups', 'field_set')}
		{/snippet}

		{#if fieldSetsLoading && fieldSets.length === 0}
			<Shimmer loading={true}>
				<div class="grid gap-3">
					{#each loadingSkeletons as s (s)}
						<div class="rounded-lg border p-4">
							<div class="space-y-1">
								<div class="h-5 w-48 rounded bg-muted"></div>
								<div class="h-4 w-32 rounded-full bg-muted"></div>
							</div>
						</div>
					{/each}
				</div>
			</Shimmer>
		{:else}
			<ul class="divide-y rounded-xl border bg-card">
				{#each visibleFieldSets as preset (preset.id)}
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

			{#if visibleFieldSets.length === 0 && !fieldSetsLoading}
				<div class="flex flex-col items-center gap-3 py-10 text-center">
					<Layers class="size-10 text-muted-foreground/50" />
					{#if fieldSets.length > 0}
						<p class="text-sm text-muted-foreground">Built-in items are hidden</p>
					{:else}
						<p class="font-medium">No saved field groups yet</p>
					{/if}
				</div>
			{/if}
		{/if}

		{#if fieldSetsHasMore}
			<div use:fieldSetsSentinel class="flex justify-center py-2" aria-hidden="true">
				{#if fieldSetsLoading}
					<div
						class="size-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground"
					></div>
				{/if}
			</div>
		{/if}
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
