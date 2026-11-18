<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { toast } from 'svelte-sonner';
	import {
		importItems,
		inspectItemImport,
		planItemImport,
		type DayMonthOrder,
		type ItemImportInspectionResponse
	} from '$lib/api/client';
	import { errorMessage, uploadErrorMessage } from '$lib/api/errors';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb/index.js';
	import CollapsibleSection from '$lib/components/collapsible-section.svelte';
	import FileDrop from '$lib/components/file-drop.svelte';
	import Page from '$lib/components/page.svelte';
	import PlanPreview from '$lib/components/plan-preview.svelte';
	import TypePicker from '$lib/components/type-picker.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { NativeSelect } from '$lib/components/ui/native-select/index.js';
	import {
		assignTarget,
		choicesFrom,
		confirmText,
		DATE_ORDERS,
		encodingName,
		hasName,
		itemsToAdd,
		mappingJson,
		rowsAndColumns,
		targetOptions,
		type ColumnChoice
	} from '$lib/csv-import';
	import type { ImportPlan } from '$lib/import-plan';

	// Three steps on one page: choose the file and the item type, match columns to fields, then
	// preview what would be added. The server keeps nothing between calls, so each one sends the
	// file again.
	type Step = 'choose' | 'match' | 'preview';

	const SEPARATORS = [
		{ value: ',', label: 'Comma' },
		{ value: ';', label: 'Semicolon' },
		{ value: '|', label: 'Pipe' }
	];
	const SAMPLES = 3;
	const STEPS = ['Choose file', 'Match columns', 'Preview'];
	const STEP_ORDER: Step[] = ['choose', 'match', 'preview'];

	let step = $state<Step>('choose');
	let file = $state<File | null>(null);
	let itemType = $state<string | null>(null);
	let separator = $state(',');
	let dateOrder = $state<DayMonthOrder>('day_first');
	let inspection = $state<ItemImportInspectionResponse | null>(null);
	let choices = $state<ColumnChoice[]>([]);
	let plan = $state<ImportPlan | null>(null);
	let loading = $state(false);
	let busy = $state(false);
	let fileError = $state<string | null>(null);
	let planError = $state<string | null>(null);

	const options = $derived(inspection ? targetOptions(inspection.fields) : []);
	const named = $derived(hasName(choices));
	// A blocked run adds nothing, so it lists no items as about to be added.
	const shown = $derived(plan && !plan.ready ? { ...plan, entities: [] } : plan);

	/** A different file or item type means the old matching no longer applies. */
	function startAgain() {
		inspection = null;
		choices = [];
		plan = null;
		fileError = null;
		planError = null;
	}

	function chooseFile(files: FileList | File[]) {
		file = files[0] ?? null;
		startAgain();
	}

	async function readFile() {
		if (!file || !itemType || loading) return;
		loading = true;
		fileError = null;
		const result = await inspectItemImport({ body: { file, item_type: itemType } });
		loading = false;
		if (result.error || !result.data) {
			fileError = uploadErrorMessage(result);
			return;
		}
		inspection = result.data;
		choices = choicesFrom(result.data.suggested_mapping);
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

	function targetOf(column: string): string {
		return choices.find((choice) => choice.column === column)?.target ?? '';
	}

	function body() {
		return {
			file: file!,
			item_type: itemType!,
			mapping: mappingJson(choices),
			list_separator: separator,
			day_month_order: dateOrder
		};
	}

	async function showPreview() {
		if (!file || !itemType || !named) return;
		step = 'preview';
		plan = null;
		planError = null;
		loading = true;
		const result = await planItemImport({ body: body() });
		loading = false;
		if (result.error || !result.data) {
			planError = uploadErrorMessage(result);
			return;
		}
		plan = result.data;
	}

	async function addItems() {
		if (busy || !file || !itemType) return;
		busy = true;
		const result = await importItems({ body: body() });
		busy = false;
		if (result.error || !result.data) {
			toast.error("Couldn't add the items", { description: errorMessage(result.error) });
			return;
		}
		const added = result.data.items_added;
		toast.success(`Added ${added.toLocaleString('en-GB')} ${added === 1 ? 'item' : 'items'}`);
		await goto(resolve('/items'));
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
							{#if index === STEP_ORDER.indexOf(step)}
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
								<option value={option.value}>{option.label}</option>
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
									value={targetOf(choice.column)}
									onchange={(e) => {
										choices = assignTarget(choices, choice.column, e.currentTarget.value || null);
									}}
								>
									<option value="">Don't import</option>
									{#each options as option (option.value)}
										<option value={option.value} disabled={option.disabled} title={option.hint}>
											{option.label}{option.disabled ? ' (not supported yet)' : ''}
										</option>
									{/each}
								</NativeSelect>
							</li>
						{/each}
					</ul>
				</div>

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
								<option value={option.value}>{option.label}</option>
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

				{#if !named}
					<p class="text-sm text-muted-foreground">Choose a column for Name.</p>
				{/if}

				<div class="flex justify-end gap-2">
					<Button variant="outline" class="pointer-coarse:h-11" onclick={() => (step = 'choose')}>
						Back
					</Button>
					<Button class="pointer-coarse:h-11" disabled={!named} onclick={showPreview}>
						Preview
					</Button>
				</div>
			{:else}
				<PlanPreview
					plan={shown}
					{loading}
					{busy}
					error={planError}
					confirmLabel={confirmText(plan ? itemsToAdd(plan) : 0)}
					cancelLabel="Back"
					onCancel={() => (step = 'match')}
					onConfirm={addItems}
				/>
			{/if}
		</Card.Content>
	</Card.Root>
</Page>
