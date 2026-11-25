<script lang="ts">
	import { onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { toast } from 'svelte-sonner';
	import {
		deleteItemImportFile,
		getItemImportFile,
		importItemImportFile,
		inspectItemImportFile,
		planItemImportFile,
		uploadItemImportFile,
		type ConnectionEnd,
		type DayMonthOrder,
		type ExtraFieldKind,
		type ImportOptionsBody,
		type ItemImportInspectionResponse,
		type ItemImportResponse,
		type NameLookup
	} from '$lib/api/client';
	import { errorMessage, uploadErrorMessage } from '$lib/api/errors';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb/index.js';
	import CollapsibleSection from '$lib/components/collapsible-section.svelte';
	import FileDrop from '$lib/components/file-drop.svelte';
	import Page from '$lib/components/page.svelte';
	import PlanPreview from '$lib/components/plan-preview.svelte';
	import ProgressPanel from '$lib/components/progress-panel.svelte';
	import { pollProgress } from '$lib/progress';
	import TypePicker from '$lib/components/type-picker.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Checkbox } from '$lib/components/ui/checkbox/index.js';
	import SuggestInput from '$lib/components/suggest-input.svelte';
	import { getCore } from '$lib/field-types';
	import { fieldNameSuggestions, matchItemField } from '$lib/field-suggestions';
	import { fetchItemFields, type ItemField } from '$lib/item-fields';
	import { NativeSelect, NativeSelectOption } from '$lib/components/ui/native-select/index.js';
	import {
		addedText,
		assignTarget,
		choicesFrom,
		confirmText,
		CONNECT,
		connectColumn,
		connectionEntries,
		connectionsReady,
		DATE_ORDERS,
		deletedRows,
		encodingName,
		fieldTitles,
		hasName,
		itemsToAdd,
		KEEP,
		keepColumn,
		keptDetails,
		KEPT_KINDS,
		keyColumns,
		keyFieldFor,
		mappingEntries,
		MAX_CONNECTED,
		MAX_KEPT,
		namedToCreate,
		renameKept,
		rowEndOptions,
		rowsAndColumns,
		setKeptKind,
		targetOptions,
		waitingText,
		type ColumnChoice
	} from '$lib/csv-import';
	import { LISTED, type ImportPlan } from '$lib/import-plan';
	import { ConnectionLookups } from '$lib/query/connection-lookups.svelte';

	// Three steps on one page: choose the file and the item type, match columns to fields, then
	// preview what would be added. The file is uploaded once and named by its id after that;
	// adding the items runs on the server, which this page follows until it ends.
	type Step = 'choose' | 'match' | 'preview' | 'adding';

	const SEPARATORS = [
		{ value: ',', label: 'Comma' },
		{ value: ';', label: 'Semicolon' },
		{ value: '|', label: 'Pipe' }
	];
	const SAMPLES = 3;
	// Rows deleted after importing, listed one by one before "and N more".
	const DELETED_SHOWN = 20;
	const MISSING: { value: NameLookup; label: string }[] = [
		{ value: 'create', label: 'Add one with just the name' },
		{ value: 'skip', label: 'Leave the connection out' }
	];
	const STEPS = ['Choose file', 'Match columns', 'Preview'];
	// Adding stays on the preview step in the breadcrumb.
	const STEP_ORDER: Step[] = ['choose', 'match', 'preview'];

	let step = $state<Step>('choose');
	const stepIndex = $derived(step === 'adding' ? 2 : STEP_ORDER.indexOf(step));
	let file = $state<File | null>(null);
	// The uploaded copy of `file`, once it has gone to the server.
	let fileId = $state<string | null>(null);
	// The import adding the items, as last read back.
	let running = $state<ItemImportResponse | null>(null);
	let itemType = $state<string | null>(null);
	let separator = $state(',');
	let dateOrder = $state<DayMonthOrder>('day_first');
	let inspection = $state<ItemImportInspectionResponse | null>(null);
	let choices = $state<ColumnChoice[]>([]);
	let plan = $state<ImportPlan | null>(null);
	// The extra details the type's items already have, for naming a kept column after one.
	let itemFields = $state<ItemField[]>([]);
	let loading = $state(false);
	let busy = $state(false);
	let fileError = $state<string | null>(null);
	let planError = $state<string | null>(null);
	// The column that recognises rows imported before, and the keys of deleted rows to bring back.
	let keyColumn = $state<string | null>(null);
	let restore = $state<string[]>([]);
	// The person's connection types, loaded once a column is connected.
	const lookups = new ConnectionLookups();

	const options = $derived(inspection ? targetOptions(inspection.fields) : []);
	const kept = $derived(keptDetails(choices));
	// Every kept detail needs a name, as every item does.
	const named = $derived(hasName(choices) && kept.every((detail) => detail.title.trim() !== ''));
	const connected = $derived(choices.filter((choice) => choice.connect).length);
	// Every connected column needs its connection type and the other item's type, too.
	const ready = $derived(named && connectionsReady(choices));
	// A blocked run adds nothing, so it lists no items as about to be added.
	const shown = $derived(plan && !plan.ready ? { ...plan, entities: [] } : plan);
	const keyChoices = $derived(keyColumns(choices));
	// A column matched elsewhere since it was chosen no longer recognises rows.
	const activeKey = $derived(
		keyColumn !== null && keyChoices.includes(keyColumn) ? keyColumn : null
	);
	const titles = $derived(inspection ? fieldTitles(choices, inspection.fields) : {});
	const deleted = $derived(plan ? deletedRows(plan, restore) : []);
	const toCreate = $derived(plan?.ready ? namedToCreate(plan) : []);

	/** A different file or item type means the old matching no longer applies. */
	function startAgain() {
		inspection = null;
		choices = [];
		plan = null;
		fileError = null;
		planError = null;
		keyColumn = null;
		restore = [];
	}

	/** Remove the uploaded copy of a file the person moved on from; it would expire anyway. */
	function discardUpload() {
		if (fileId) void deleteItemImportFile({ path: { file_id: fileId } });
		fileId = null;
	}

	// Leaving before adding the items removes the uploaded copy; once queued it is the server's.
	onDestroy(() => {
		if (step !== 'adding') discardUpload();
	});

	function chooseFile(files: FileList | File[]) {
		discardUpload();
		file = files[0] ?? null;
		startAgain();
	}

	/** Upload the chosen file once; later steps name it by id. */
	async function uploaded(chosen: File): Promise<string | null> {
		if (fileId) return fileId;
		const result = await uploadItemImportFile({
			body: chosen,
			headers: { 'X-Filename': encodeURIComponent(chosen.name) }
		});
		if (result.error || !result.data) {
			fileError = uploadErrorMessage(result);
			return null;
		}
		fileId = result.data.id;
		return fileId;
	}

	async function readFile() {
		if (!file || !itemType || loading) return;
		loading = true;
		fileError = null;
		const id = await uploaded(file);
		if (!id) {
			loading = false;
			return;
		}
		// The type's existing details come with the file, so a kept column can join one at once.
		const [result, fields] = await Promise.all([
			inspectItemImportFile({ path: { file_id: id }, body: { item_type: itemType } }),
			fetchItemFields(itemType)
		]);
		loading = false;
		if (result.error || !result.data) {
			fileError = uploadErrorMessage(result);
			return;
		}
		inspection = result.data;
		choices = choicesFrom(result.data.suggested_mapping);
		// Suggestions only; the import works the same without them.
		itemFields = fields ?? [];
		dateOrder = result.data.day_month_order ?? 'day_first';
		step = 'match';
	}

	function samples(column: string): string {
		const values = (inspection?.sample_rows ?? [])
			.map((row) => row[column]?.trim())
			.filter((value): value is string => !!value)
			.slice(0, SAMPLES);
		return values.length > 0 ? values.join(' · ') : 'Nothing in the first rows';
	}

	function targetOf(choice: ColumnChoice): string {
		if (choice.connect) return CONNECT;
		return choice.extra ? KEEP : (choice.target ?? '');
	}

	function choose(column: string, value: string) {
		if (value === CONNECT) {
			choices = connectColumn(choices, column);
			void lookups.loadRelationships();
			return;
		}
		if (value !== KEEP) {
			choices = assignTarget(choices, column, value || null);
			return;
		}
		choices = keepColumn(choices, column, inspection?.column_kinds?.[column] ?? 'text');
		// A header that names a detail the items already have joins it from the start.
		if (matchItemField(column, itemFields, KEPT_KINDS)) nameKept(column, column);
	}

	const kindLabel = (kind: ExtraFieldKind) => getCore(kind)?.label ?? kind;
	const nameSuggestions = $derived(fieldNameSuggestions(itemFields, KEPT_KINDS));

	/** A name the type's items already use joins that detail: same key, same kind. */
	function nameKept(column: string, title: string) {
		const match = matchItemField(title, itemFields, KEPT_KINDS);
		choices = renameKept(
			choices,
			column,
			title,
			match && { key: match.key, kind: match.kind as ExtraFieldKind }
		);
	}

	const joined = (key: string | undefined) =>
		key === undefined ? undefined : itemFields.find((field) => field.key === key);

	const relationshipOf = (slug: string | null) =>
		lookups.relationships?.find((relationship) => relationship.slug === slug);

	function importOptions(): ImportOptionsBody {
		const fieldKeys = (inspection?.fields ?? []).map((f) => f.key);
		return {
			item_type: itemType!,
			mapping: mappingEntries(choices, fieldKeys),
			list_separator: separator,
			day_month_order: dateOrder,
			key_field: keyFieldFor(choices, fieldKeys, activeKey),
			restore,
			connections: connectionEntries(choices)
		};
	}

	async function showPreview() {
		if (!fileId || !itemType || !ready) return;
		step = 'preview';
		plan = null;
		restore = [];
		await planAgain();
	}

	/** Work the preview out again; the one shown stays until the new one arrives. */
	async function planAgain() {
		if (!fileId) return;
		planError = null;
		loading = true;
		const result = await planItemImportFile({ path: { file_id: fileId }, body: importOptions() });
		loading = false;
		if (result.error || !result.data) {
			planError = uploadErrorMessage(result);
			return;
		}
		plan = result.data;
	}

	function bringBack(key: string, on: boolean) {
		restore = on ? [...restore, key] : restore.filter((k) => k !== key);
		void planAgain();
	}

	function bringAllBack() {
		restore = deleted.map((row) => row.key);
		void planAgain();
	}

	async function addItems() {
		if (busy || !fileId || !itemType) return;
		busy = true;
		const result = await importItemImportFile({ path: { file_id: fileId }, body: importOptions() });
		busy = false;
		if (result.error || !result.data) {
			toast.error("Couldn't add the items", { description: errorMessage(result.error) });
			return;
		}
		running = result.data;
		step = 'adding';
	}

	async function readImport(id: string): Promise<ItemImportResponse | null> {
		const result = await getItemImportFile({ path: { file_id: id } });
		return result.data ?? null;
	}

	// Follow the import until it ends; it carries on if the person leaves.
	$effect(() => {
		const id = running?.id;
		if (step !== 'adding' || !id) return;
		return pollProgress(
			() => readImport(id),
			(latest) => {
				if (latest) running = latest;
			}
		);
	});

	$effect(() => {
		if (step !== 'adding' || running?.status !== 'succeeded') return;
		toast.success(addedText(running.result ?? { items_added: 0, connections_added: 0 }));
		void goto(resolve('/items'));
	});

	/** After a failed import the file has gone, so it is chosen again from the start. */
	function tryAgain() {
		running = null;
		fileId = null;
		file = null;
		startAgain();
		step = 'choose';
	}
</script>

<svelte:head>
	<title>Import items - Menagerist</title>
</svelte:head>

<Page width="form">
	<Card.Root>
		<Card.Header>
			<Card.Title class="font-heading text-xl">Import items from a CSV</Card.Title>
			<Breadcrumb.Root>
				<Breadcrumb.List>
					{#each STEPS as name, index (name)}
						<Breadcrumb.Item>
							{#if index === stepIndex}
								<Breadcrumb.Page class="font-semibold">{name}</Breadcrumb.Page>
							{:else}
								<span>{name}</span>
							{/if}
						</Breadcrumb.Item>
						{#if index < STEPS.length - 1}
							<Breadcrumb.Separator />
						{/if}
					{/each}
				</Breadcrumb.List>
			</Breadcrumb.Root>
			<Card.Description>
				{#if step === 'choose'}
					Each row of the file becomes an item.
				{:else if step === 'match' && inspection}
					{rowsAndColumns(inspection)}. Read as {encodingName(inspection.encoding)}.
				{/if}
			</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-5">
			{#if step === 'choose'}
				<div class="space-y-2">
					<p class="text-sm font-medium">File</p>
					<FileDrop
						multiple={false}
						accept=".csv,text/csv"
						label={file?.name}
						disabled={loading}
						onFiles={chooseFile}
					/>
					{#if fileError}
						<p class="text-sm text-destructive" role="alert">{fileError}</p>
					{/if}
				</div>

				<div class="space-y-2">
					<p class="text-sm font-medium">Item type</p>
					<TypePicker
						bind:value={itemType}
						allowClear={false}
						allowCreate={false}
						disabled={loading}
						onchange={startAgain}
					/>
					<p class="text-xs text-muted-foreground">
						The items are added under this type. Make the type first if it does not exist yet.
					</p>
				</div>

				<CollapsibleSection id="csv-import-options" title="More options" defaultOpen={false}>
					<div class="space-y-1.5">
						<label class="text-sm font-medium" for="csv-separator">List separator</label>
						<NativeSelect
							id="csv-separator"
							class="w-full sm:w-48 pointer-coarse:[&_select]:min-h-11"
							value={separator}
							onchange={(e) => (separator = e.currentTarget.value)}
						>
							{#each SEPARATORS as option (option.value)}
								<NativeSelectOption value={option.value}>{option.label}</NativeSelectOption>
							{/each}
						</NativeSelect>
						<p class="text-xs text-muted-foreground">
							Splits a cell that holds several values, such as tags.
						</p>
					</div>
				</CollapsibleSection>

				<div class="flex justify-end gap-2">
					<Button
						variant="outline"
						class="pointer-coarse:h-11"
						disabled={loading}
						href={resolve('/items')}
					>
						Cancel
					</Button>
					<Button
						class="pointer-coarse:h-11"
						disabled={!file || !itemType || loading}
						onclick={readFile}
					>
						{loading ? 'Reading…' : 'Next'}
					</Button>
				</div>
			{:else if step === 'match'}
				<div class="space-y-3">
					<div
						class="hidden gap-3 text-xs font-medium text-muted-foreground sm:grid sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_14rem]"
					>
						<span>Column</span>
						<span>First values</span>
						<span>Goes into</span>
					</div>
					<ul class="space-y-3">
						{#each choices as choice, index (choice.column)}
							<li
								class="grid gap-1.5 rounded-lg border p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_14rem] sm:items-center sm:gap-3 sm:rounded-none sm:border-0 sm:border-b sm:p-0 sm:pb-3"
							>
								<label class="text-sm font-medium break-words" for={`csv-column-${index}`}>
									{choice.column}
								</label>
								<span class="text-sm break-words text-muted-foreground">
									{samples(choice.column)}
								</span>
								<NativeSelect
									id={`csv-column-${index}`}
									class="w-full pointer-coarse:[&_select]:min-h-11"
									value={targetOf(choice)}
									onchange={(e) => choose(choice.column, e.currentTarget.value)}
								>
									<NativeSelectOption value="">Don't import</NativeSelectOption>
									{#each options as option (option.value)}
										<NativeSelectOption
											value={option.value}
											disabled={option.disabled}
											title={option.hint}
										>
											{option.label}{option.disabled ? ' (not supported yet)' : ''}
										</NativeSelectOption>
									{/each}
									<NativeSelectOption
										value={KEEP}
										disabled={!choice.extra && kept.length >= MAX_KEPT}
									>
										Keep as an extra detail
									</NativeSelectOption>
									<NativeSelectOption
										value={CONNECT}
										disabled={!choice.connect && connected >= MAX_CONNECTED}
									>
										Connect to an item by name
									</NativeSelectOption>
								</NativeSelect>
								{#if choice.connect}
									{@const connect = choice.connect}
									{@const relationship = relationshipOf(connect.relationship_type)}
									<div class="grid gap-2 sm:col-span-3 sm:grid-cols-2 sm:pl-4">
										<div class="space-y-1">
											<label
												class="text-xs text-muted-foreground"
												for={`csv-connect-type-${index}`}
											>
												Connection type
											</label>
											<NativeSelect
												id={`csv-connect-type-${index}`}
												class="w-full pointer-coarse:[&_select]:min-h-11"
												value={connect.relationship_type ?? ''}
												disabled={!lookups.relationships}
												onchange={(e) =>
													(choices = connectColumn(choices, choice.column, {
														relationship_type: e.currentTarget.value || null
													}))}
											>
												<NativeSelectOption value="">
													{lookups.relationships ? 'Choose a connection type' : 'Loading…'}
												</NativeSelectOption>
												{#each lookups.relationships ?? [] as option (option.slug)}
													<NativeSelectOption value={option.slug}>
														{option.label}
													</NativeSelectOption>
												{/each}
											</NativeSelect>
											{#if lookups.relationshipsFailed}
												<p class="text-xs text-destructive" role="alert">
													Couldn't load your connection types.
													<button
														type="button"
														class="underline underline-offset-2"
														onclick={() => lookups.retryRelationships()}
													>
														Try again
													</button>
												</p>
											{/if}
										</div>
										<div class="space-y-1">
											<p class="text-xs text-muted-foreground">The other item's type</p>
											<TypePicker
												value={connect.item_type}
												allowClear={false}
												allowCreate={false}
												aria-label={`The other item's type for ${choice.column}`}
												onchange={(slug) =>
													(choices = connectColumn(choices, choice.column, { item_type: slug }))}
											/>
										</div>
										{#if relationship?.directional}
											<div class="space-y-1 sm:col-span-2">
												<label
													class="text-xs text-muted-foreground"
													for={`csv-connect-end-${index}`}
												>
													Which way
												</label>
												<NativeSelect
													id={`csv-connect-end-${index}`}
													class="w-full pointer-coarse:[&_select]:min-h-11"
													value={connect.row_end}
													onchange={(e) =>
														(choices = connectColumn(choices, choice.column, {
															row_end: e.currentTarget.value as ConnectionEnd
														}))}
												>
													{#each rowEndOptions(relationship) as option (option.value)}
														<NativeSelectOption value={option.value}>
															{option.label}
														</NativeSelectOption>
													{/each}
												</NativeSelect>
											</div>
										{/if}
										<div class="space-y-1 sm:col-span-2">
											<label
												class="text-xs text-muted-foreground"
												for={`csv-connect-missing-${index}`}
											>
												If you have no item with that name
											</label>
											<NativeSelect
												id={`csv-connect-missing-${index}`}
												class="w-full pointer-coarse:[&_select]:min-h-11"
												value={connect.on_missing}
												onchange={(e) =>
													(choices = connectColumn(choices, choice.column, {
														on_missing: e.currentTarget.value as NameLookup
													}))}
											>
												{#each MISSING as option (option.value)}
													<NativeSelectOption value={option.value}>
														{option.label}
													</NativeSelectOption>
												{/each}
											</NativeSelect>
										</div>
										<p class="text-xs text-muted-foreground sm:col-span-2">
											Each row connects to the item its cell names. Names are matched whatever their
											capitals and spacing, and each name is added once.
										</p>
									</div>
								{/if}
								{#if choice.extra}
									{@const extra = choice.extra}
									<div class="grid gap-2 sm:col-span-3 sm:grid-cols-[minmax(0,1fr)_14rem] sm:pl-4">
										<div class="space-y-1">
											<label class="text-xs text-muted-foreground" for={`csv-kept-name-${index}`}>
												Detail name
											</label>
											<SuggestInput
												id={`csv-kept-name-${index}`}
												value={extra.title}
												suggestions={nameSuggestions}
												oninput={(title) => nameKept(choice.column, title)}
											/>
										</div>
										<div class="space-y-1">
											<label class="text-xs text-muted-foreground" for={`csv-kept-kind-${index}`}>
												Kind
											</label>
											<NativeSelect
												id={`csv-kept-kind-${index}`}
												class="w-full pointer-coarse:[&_select]:min-h-11"
												value={extra.kind}
												onchange={(e) =>
													(choices = setKeptKind(
														choices,
														choice.column,
														e.currentTarget.value as ExtraFieldKind
													))}
											>
												{#each KEPT_KINDS as kind (kind)}
													<NativeSelectOption value={kind}>{kindLabel(kind)}</NativeSelectOption>
												{/each}
											</NativeSelect>
										</div>
										<p class="text-xs text-muted-foreground sm:col-span-2">
											{#if joined(extra.key)}
												{@const field = joined(extra.key)!}
												Joins the {field.label} detail already on {field.count === 1
													? '1 item'
													: `${field.count.toLocaleString('en-GB')} items`}.
											{/if}
											{extra.kind === 'choice'
												? 'Each item gets this detail for itself, with every different value in the column to choose from.'
												: 'Each item gets this detail for itself. Add it to the item type later to give every item the field.'}
										</p>
									</div>
								{/if}
							</li>
						{/each}
					</ul>
				</div>

				{#if keyChoices.length > 0}
					<div class="space-y-1.5">
						<label class="text-sm font-medium" for="csv-key">
							Recognise rows already imported by
						</label>
						<NativeSelect
							id="csv-key"
							class="w-full sm:w-80 pointer-coarse:[&_select]:min-h-11"
							value={activeKey ?? ''}
							onchange={(e) => (keyColumn = e.currentTarget.value || null)}
						>
							<NativeSelectOption value="">Nothing: add every row</NativeSelectOption>
							{#each keyChoices as column (column)}
								<NativeSelectOption value={column}>{column}</NativeSelectOption>
							{/each}
						</NativeSelect>
						<p class="text-xs text-muted-foreground">
							Pick a column that is different on every row, such as an ID. Importing the file again
							then adds only the new rows, and leaves out any you deleted.
						</p>
					</div>
				{/if}

				{#if inspection?.day_month_order}
					<div class="space-y-1.5">
						<label class="text-sm font-medium" for="csv-date-order">Dates like 03/04/2019</label>
						<NativeSelect
							id="csv-date-order"
							class="w-full sm:w-80 pointer-coarse:[&_select]:min-h-11"
							value={dateOrder}
							onchange={(e) => (dateOrder = e.currentTarget.value as DayMonthOrder)}
						>
							{#each DATE_ORDERS as option (option.value)}
								<NativeSelectOption value={option.value}>{option.label}</NativeSelectOption>
							{/each}
						</NativeSelect>
						<p class="text-xs text-muted-foreground">
							{inspection.day_month_order_certain
								? 'Chosen from the dates in the file.'
								: 'The dates do not settle this, so day first is a guess.'}
							Two-digit years from 00 to 49 are 2000 to 2049, and 50 to 99 are 1950 to 1999.
						</p>
					</div>
				{/if}

				{#if inspection?.fields.some((f) => f.kind === 'date' || f.kind === 'partialdate')}
					<p class="text-xs text-muted-foreground">
						Excel shows <span class="font-mono">Oct-18</span> for a full date it formatted as month and
						year, and saves it that way. To keep the day, set the column to dd/mm/yyyy before saving as
						CSV.
					</p>
				{/if}

				{#if !hasName(choices)}
					<p class="text-sm text-muted-foreground">Choose a column for Name.</p>
				{:else if !named}
					<p class="text-sm text-muted-foreground">Give each extra detail a name.</p>
				{:else if !ready}
					<p class="text-sm text-muted-foreground">
						Choose a connection type and the other item's type for each connected column.
					</p>
				{/if}

				<div class="flex justify-end gap-2">
					<Button variant="outline" class="pointer-coarse:h-11" onclick={() => (step = 'choose')}>
						Back
					</Button>
					<Button class="pointer-coarse:h-11" disabled={!ready} onclick={showPreview}>
						Preview
					</Button>
				</div>
			{:else if step === 'adding' && running}
				{#if running.status === 'failed'}
					<div class="space-y-1" role="alert">
						<p class="text-sm font-medium">The items couldn't be added</p>
						<p class="text-sm text-muted-foreground">{running.failure}</p>
					</div>
					<div class="flex justify-end">
						<Button class="pointer-coarse:h-11" onclick={tryAgain}>Choose a file</Button>
					</div>
				{:else}
					<ProgressPanel
						snapshot={running.status === 'running' ? (running.progress ?? null) : null}
						label="Adding the items"
						fallback={running.status === 'queued' ? waitingText(running.ahead) : 'Starting…'}
					/>
					<p class="text-sm text-muted-foreground">
						You can leave this page; the items are still added.
					</p>
				{/if}
			{:else}
				{#if kept.length > 0}
					<p class="text-sm text-muted-foreground">
						Each item also gets {kept.length === 1 ? 'an extra detail' : 'extra details'} of its own when
						its cell has a value: {kept
							.map((detail) => `${detail.title.trim()} (${kindLabel(detail.kind)})`)
							.join(', ')}.
					</p>
				{/if}
				{#if toCreate.length > 0}
					<p class="text-sm text-muted-foreground">
						New items from connected columns, with just their names: {toCreate
							.slice(0, LISTED)
							.join(', ')}{toCreate.length > LISTED
							? ` and ${(toCreate.length - LISTED).toLocaleString('en-GB')} more`
							: ''}.
					</p>
				{/if}
				{#if deleted.length > 0}
					<section class="space-y-2" aria-label="Deleted after importing">
						<h3 class="text-sm font-medium">Deleted after importing</h3>
						<p class="text-xs text-muted-foreground">
							You deleted {deleted.length === 1 ? 'this' : 'these'} after an earlier import, so
							{deleted.length === 1 ? 'it is' : 'they are'} left out. Tick one to bring it back.
						</p>
						<ul class="space-y-1.5">
							{#each deleted.slice(0, DELETED_SHOWN) as row, index (row.key)}
								<li class="flex items-center gap-2 text-sm">
									<Checkbox
										id={`csv-restore-${index}`}
										checked={row.restored}
										disabled={loading}
										onCheckedChange={(on) => bringBack(row.key, on === true)}
									/>
									<label for={`csv-restore-${index}`}>{row.label}</label>
								</li>
							{/each}
							{#if deleted.length > DELETED_SHOWN}
								<li class="text-sm text-muted-foreground">
									and {(deleted.length - DELETED_SHOWN).toLocaleString('en-GB')} more
								</li>
							{/if}
						</ul>
						{#if deleted.some((row) => !row.restored)}
							<Button
								variant="outline"
								size="sm"
								class="pointer-coarse:h-11"
								disabled={loading}
								onclick={bringAllBack}
							>
								Bring them all back
							</Button>
						{/if}
					</section>
				{/if}
				<PlanPreview
					plan={shown}
					{loading}
					{busy}
					error={planError}
					fieldTitles={titles}
					confirmLabel={confirmText(plan ? itemsToAdd(plan) : 0)}
					cancelLabel="Back"
					onCancel={() => (step = 'match')}
					onConfirm={addItems}
				/>
			{/if}
		</Card.Content>
	</Card.Root>
</Page>
