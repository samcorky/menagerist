<script lang="ts">
	import { Plus, ScanBarcode, X } from '@lucide/svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';
	import { rowsToAttributes } from '$lib/attribute-rows';
	import type { AttributeRow, GroupRow } from '$lib/attribute-rows';
	import type { AttributesSchema, JsonSchemaProperty, EditorField } from '$lib/schema-types';
	import { generateFieldKey } from '$lib/field-key';
	import {
		mergeAttributeSchemas,
		readPropMeta,
		readSchemaMeta,
		validationSchema
	} from '$lib/schema-meta';
	import BarcodeScanner from '$lib/components/barcode-scanner.svelte';
	import { isSection, schemaToItems, itemsToSchema } from '$lib/schema-editor-items';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { normalise, isSectionItem } from '$lib/layout';
	import { coreForProp } from '$lib/field-types';
	import { describeConstraints, parseConstraints } from '$lib/field-types/text/constraints';
	import { createSafeValidator } from '$lib/safe-validator';
	import { friendlyClientError, topLevelKey } from '$lib/validation-messages';
	import { listAttributeValues, promoteExtraSchemaField } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import FieldKindRow from '$lib/components/field-kind-row.svelte';
	import SuggestInput from '$lib/components/suggest-input.svelte';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';
	import { fetchItemFields, type ItemField } from '$lib/item-fields';
	import { fieldNameSuggestions, matchItemField } from '$lib/field-suggestions';
	import { changeKind } from '$lib/field-types/kind-changes';
	import PresetPickerDialog from '$lib/components/preset-picker-dialog.svelte';
	import { definitionToFieldSet, type FieldSetDefinition, type Preset } from '$lib/presets';

	/** Matches the backend's `MAX_EXTRA_SCHEMA_FIELDS` (extra_schema_limits.py). */
	const MAX_EXTRA_SCHEMA_FIELDS = 50;

	let {
		rows = $bindable(),
		schema = null,
		extraSchema = $bindable(null),
		supportsExtraFields = false,
		nodeId,
		nodeType,
		onPromoted,
		serverErrors = null,
		only
	}: {
		rows: AttributeRow[];
		schema?: AttributesSchema | null;
		extraSchema?: AttributesSchema | null;
		supportsExtraFields?: boolean;
		nodeId?: string;
		/** The item's type: its id for value suggestions, and its slug and label to promote a field. */
		nodeType?: { id: string; slug: string; label: string };
		onPromoted?: () => void;
		serverErrors?: Record<string, string> | null;
		/** Show just these fields of `schema`, flat and in this order, with nothing else (quick capture). */
		only?: readonly string[];
	} = $props();

	let mergedSchema = $derived(mergeAttributeSchemas(schema, extraSchema));

	// Required is advisory and never blocks, so validate without it.
	let validator = $derived(
		mergedSchema
			? createSafeValidator(validationSchema($state.snapshot(mergedSchema)) as object)
			: null
	);

	const touched = new SvelteSet<string>();

	// The field the last scan button was pressed for; the scanner closes before it reports.
	let scanKey = $state<string | null>(null);
	let scannerOpen = $state(false);

	let clientErrors = $derived.by(() => {
		const errors: Record<string, string> = {};
		if (!validator || !mergedSchema) return errors;
		for (const err of validator.validate(rowsToAttributes(rows, mergedSchema))) {
			const key = topLevelKey(err.instanceLocation);
			if (key && !errors[key]) errors[key] = friendlyClientError(mergedSchema, err);
		}
		return errors;
	});

	// Server errors show immediately; client errors only once the field has been left.
	let fieldErrors = $derived.by(() => {
		const errors: Record<string, string> = { ...serverErrors };
		for (const [key, message] of Object.entries(clientErrors)) {
			if (!errors[key] && touched.has(key)) errors[key] = message;
		}
		return errors;
	});

	function markTouched(key: string) {
		touched.add(key);
	}

	let requiredKeys = $derived(mergedSchema ? (readSchemaMeta(mergedSchema).required ?? []) : []);
	let schemaLayout = $derived(
		schema ? normalise(readSchemaMeta(schema).layout, schema.properties) : []
	);
	let extraLayout = $derived(
		extraSchema ? normalise(readSchemaMeta(extraSchema).layout, extraSchema.properties) : []
	);
	let extraFieldCount = $derived(Object.keys(extraSchema?.properties ?? {}).length);

	function getValue(key: string): unknown {
		return rows.find((r) => r.key === key)?.value ?? '';
	}

	function isEmptyValue(value: unknown): boolean {
		if (value === null || value === undefined || value === '') return true;
		if (Array.isArray(value)) return value.length === 0;
		if (typeof value === 'object') {
			return Object.values(value).every((v) => v === '' || v === null || v === undefined);
		}
		return false;
	}

	function setValue(key: string, value: unknown) {
		const existing = rows.find((r) => r.key === key);
		if (existing) {
			rows = rows.map((r) =>
				r.key === key ? { ...r, value: value as string | GroupRow[] | GroupRow } : r
			);
		} else {
			rows = [...rows, { key, value: value as string | GroupRow[] | GroupRow }];
		}
	}

	// -- Values used before, offered by the browser on text fields (#680) ----------

	// Kept per field, so a field never shows another field's values.
	let valueSuggestions = $state<Record<string, string[]>>({});
	let suggestTimer: ReturnType<typeof setTimeout> | undefined;

	async function fetchValues(key: string, q: string) {
		if (!nodeType) return;
		const result = await listAttributeValues({
			path: { node_type_id: nodeType.id, key },
			query: q ? { q, limit: 20 } : { limit: 20 }
		});
		if (result.data) {
			valueSuggestions = { ...valueSuggestions, [key]: result.data.map((v) => v.value) };
		}
	}

	/** The most used values on focus; matches for what is typed once typing pauses. */
	function suggestValues(key: string, q: string, wait = 250) {
		clearTimeout(suggestTimer);
		suggestTimer = setTimeout(() => void fetchValues(key, q.trim()), wait);
	}

	// -- Overlay field creation ("Add field") -----------------------------------

	let addingField = $state(false);
	let draftField = $state<EditorField | null>(null);
	// Extra details other items of the type have, offered as names; one chosen is joined.
	let otherFields = $state<ItemField[]>([]);
	let joining = $state<ItemField | null>(null);

	const takenKeys = () => [
		...Object.keys(schema?.properties ?? {}),
		...Object.keys(extraSchema?.properties ?? {})
	];

	function nameDraft(label: string) {
		if (!draftField) return;
		joining = matchItemField(label, otherFields) ?? null;
		const named = { ...draftField, label };
		draftField = joining && joining.kind !== named.kind ? changeKind(named, joining.kind) : named;
	}

	function changeDraft(field: EditorField) {
		// Another kind is another field, so it no longer joins one.
		if (joining && field.kind !== joining.kind) joining = null;
		draftField = field;
	}

	function newDraftField(): EditorField {
		return {
			key: '',
			keyPending: true,
			label: '',
			kind: 'text',
			required: false,
			options: [],
			subFields: []
		};
	}

	function startAddField() {
		draftField = newDraftField();
		joining = null;
		addingField = true;
		if (nodeType) {
			const taken = new Set(takenKeys());
			void fetchItemFields(nodeType.slug).then((found) => {
				otherFields = (found ?? []).filter((f) => !taken.has(f.key));
				// A name typed before they arrived still joins its detail.
				if (draftField?.label) nameDraft(draftField.label);
			});
		}
	}

	function cancelAddField() {
		addingField = false;
		draftField = null;
	}

	function confirmAddField() {
		if (!draftField || !draftField.label.trim()) return;
		const taken = takenKeys();
		const key =
			joining && !taken.includes(joining.key)
				? joining.key
				: generateFieldKey(draftField.label, taken);
		const items = schemaToItems(extraSchema).filter((i): i is EditorField => !isSection(i));
		const nextItems = [...items, { ...draftField, key, keyPending: false }];
		extraSchema = itemsToSchema(nextItems, readSchemaMeta(extraSchema), []);
		rows = [...rows, { key, value: draftField.kind === 'boolean' ? 'false' : '' }];
		addingField = false;
		draftField = null;
		joining = null;
	}

	function removeExtraField(key: string) {
		if (!extraSchema) return;
		const remainingItems = schemaToItems(extraSchema)
			.filter((i): i is EditorField => !isSection(i))
			.filter((f) => f.key !== key);
		const removedField = schemaToItems(extraSchema).find(
			(i): i is EditorField => !isSection(i) && i.key === key
		);
		const previousExtraSchema = extraSchema;
		const previousRows = $state.snapshot(rows) as AttributeRow[];
		// itemsToSchema returns null for an empty item list, but the backend's
		// UpdateNode treats a null extra_schema as "leave unchanged" (same fix as
		// PromoteExtraSchemaField) - build a real, empty schema instead so removing
		// the last overlay field and saving actually clears it server-side.
		extraSchema = itemsToSchema(remainingItems, readSchemaMeta(extraSchema), []) ?? {
			$schema: 'https://json-schema.org/draft/2020-12/schema',
			type: 'object',
			properties: {}
		};
		rows = rows.filter((r) => r.key !== key);
		toast(`${removedField?.label || 'Field'} removed`, {
			action: {
				label: 'Undo',
				onClick: () => {
					extraSchema = previousExtraSchema;
					rows = previousRows;
				}
			},
			duration: 5000
		});
	}

	// Ad hoc field groups ("Add saved field group") -----------------------------

	let fieldSetPickerOpen = $state(false);

	function addFieldSetFromPreset(preset: Preset) {
		const definition = preset.definition as FieldSetDefinition;
		const section = definitionToFieldSet(
			definition,
			{ preset: preset.id, version: preset.version },
			'field-set'
		);
		const taken = [
			...Object.keys(schema?.properties ?? {}),
			...Object.keys(extraSchema?.properties ?? {})
		];
		const newFields: EditorField[] = [];
		for (const field of section.fields) {
			const key = generateFieldKey(field.label, [...taken, ...newFields.map((f) => f.key)]);
			newFields.push({ ...field, key, keyPending: false });
		}
		const items = schemaToItems(extraSchema).filter((i): i is EditorField => !isSection(i));
		extraSchema = itemsToSchema([...items, ...newFields], readSchemaMeta(extraSchema), []);
		rows = [
			...rows,
			...newFields.map((f) => ({ key: f.key, value: f.kind === 'boolean' ? 'false' : '' }))
		];
	}

	let promotingKey = $state<string | null>(null);
	// A field other items of the type also carry, waiting for the person to confirm.
	let promoteAsk = $state<{ key: string; label: string; others: number } | null>(null);

	// Promoting moves the field off every item of the type that has it, so say how many first.
	async function askToPromote(key: string, label: string) {
		if (!nodeType) return;
		promotingKey = key;
		const fields = await fetchItemFields(nodeType.slug);
		const count = fields?.filter((f) => f.key === key).reduce((sum, f) => sum + f.count, 0) ?? 0;
		promotingKey = null;
		if (count > 1) promoteAsk = { key, label, others: count - 1 };
		else await promoteField(key);
	}

	async function promoteField(key: string) {
		if (!nodeId || !nodeType) return;
		promotingKey = key;
		const result = await promoteExtraSchemaField({
			path: { node_id: nodeId, key },
			body: { node_type_id: nodeType.id }
		});
		promotingKey = null;
		promoteAsk = null;
		if (result.error) {
			toast.error("Couldn't make this a field", { description: errorMessage(result.error) });
			return;
		}
		toast.success(`Field added to ${nodeType.label}`);
		onPromoted?.();
	}
</script>

{#snippet fieldEntry(key: string, prop: JsonSchemaProperty, overlay: boolean = false)}
	{@const isRequired = requiredKeys.includes(key)}
	{@const error = fieldErrors[key]}
	{@const desc = coreForProp(prop)}
	{@const Widget = desc?.InputWidget}
	{@const parsed =
		prop.type === 'string'
			? parseConstraints(prop as { pattern?: unknown; allOf?: unknown })
			: null}
	{@const rule = parsed && !parsed.custom ? describeConstraints(parsed.constraints) : null}
	<div
		class="-mx-2 flex flex-col gap-2 rounded-md p-2 transition-colors focus-within:bg-muted/40 sm:flex-row {prop.type ===
		'array'
			? 'sm:items-start'
			: 'sm:items-center'}"
		onfocusout={() => markTouched(key)}
	>
		<span class="w-full pt-1.5 text-sm text-muted-foreground sm:w-32 sm:shrink-0">
			{prop.title || key}{#if isRequired}{#if isEmptyValue(getValue(key))}<span
						class="ml-1 text-xs text-muted-foreground"
					>
						Recommended
					</span>{:else}<span class="ml-0.5 text-muted-foreground">
						*
					</span>{/if}{/if}{#if overlay}<span
					class="ml-1.5 rounded border border-input px-1.5 text-xs text-muted-foreground"
				>
					This item only
				</span>{/if}
		</span>
		<div class="flex flex-1 flex-col gap-1">
			<div class="flex items-start gap-2">
				<div
					class="min-w-0 flex-1 rounded-md transition-colors duration-150 {error
						? 'ring-1 ring-destructive/60'
						: ''}"
				>
					{#if desc?.kind === 'text' && nodeType}
						{@const currentValue = typeof getValue(key) === 'string' ? String(getValue(key)) : ''}
						<SuggestInput
							value={currentValue}
							suggestions={valueSuggestions[key] ?? []}
							oninput={(v) => {
								setValue(key, v);
								suggestValues(key, v);
							}}
							onfocus={() => suggestValues(key, currentValue, 0)}
							class="flex-1"
							aria-label={prop.title || key}
							aria-invalid={!!error}
						/>
					{:else if Widget}
						<Widget
							value={getValue(key)}
							onChange={(v) => setValue(key, v)}
							ariaLabel={prop.title || key}
							{prop}
						/>
					{:else}
						<Input
							value={typeof getValue(key) === 'string' ? String(getValue(key)) : ''}
							oninput={(e) => setValue(key, (e.target as HTMLInputElement).value)}
							class="flex-1"
							aria-label={prop.title || key}
							aria-invalid={!!error}
						/>
					{/if}
				</div>
				{#if desc?.kind === 'text' && readPropMeta(prop).barcode === true}
					<Button
						type="button"
						variant="outline"
						size="icon"
						class="shrink-0"
						aria-label="Scan barcode into {prop.title || key}"
						onclick={() => {
							scanKey = key;
							scannerOpen = true;
						}}
					>
						<ScanBarcode class="size-4" />
					</Button>
				{/if}
			</div>
			{#if error}
				<p class="text-xs text-destructive">{error}</p>
			{:else if rule}
				<p class="text-xs text-muted-foreground">{rule}</p>
			{/if}
		</div>
	</div>
{/snippet}

<div class="space-y-2">
	{#if !only}
		<Label>Details</Label>
	{/if}
	{#if validator?.degraded}
		<p class="text-xs text-muted-foreground" role="status">
			Some rules could not be checked here. They are still checked when you save.
		</p>
	{/if}

	{#if only}
		{#each only as key (key)}
			{#if schema && key in schema.properties}
				{@render fieldEntry(key, schema.properties[key])}
			{/if}
		{/each}
	{:else if schema && schemaLayout.length > 0}
		{#each schemaLayout as layoutItem (isSectionItem(layoutItem) ? layoutItem.id : layoutItem.key)}
			{#if isSectionItem(layoutItem)}
				<div class="space-y-2 pt-1">
					<p class="text-xs font-medium tracking-wide text-muted-foreground uppercase">
						{layoutItem.section}
					</p>
					<div class="space-y-2 rounded-md border border-input/60 bg-muted/20 p-3">
						{#each layoutItem.items as { key } (key)}
							{#if key in schema.properties}
								{@render fieldEntry(key, schema.properties[key])}
							{/if}
						{/each}
					</div>
				</div>
			{:else if layoutItem.key in schema.properties}
				{@render fieldEntry(layoutItem.key, schema.properties[layoutItem.key])}
			{/if}
		{/each}
	{/if}

	{#if !only && extraSchema && extraLayout.length > 0}
		{#each extraLayout as layoutItem (isSectionItem(layoutItem) ? layoutItem.id : layoutItem.key)}
			{#if !isSectionItem(layoutItem) && layoutItem.key in extraSchema.properties}
				{@const key = layoutItem.key}
				{@const prop = extraSchema.properties[key]}
				<div class="flex flex-col gap-2 sm:flex-row sm:items-start">
					<div class="min-w-0 flex-1">
						{@render fieldEntry(key, prop, true)}
					</div>
					<div class="flex flex-wrap items-center gap-2 sm:shrink-0">
						{#if supportsExtraFields && nodeId && nodeType}
							<Button
								type="button"
								variant="ghost"
								size="sm"
								class="mt-1 h-7 text-xs"
								disabled={promotingKey === key}
								onclick={() => askToPromote(key, prop.title || key)}
							>
								Make this a field
							</Button>
						{/if}
						<Button
							type="button"
							variant="ghost"
							size="icon"
							class="mt-1"
							onclick={() => removeExtraField(key)}
							aria-label="Remove field"
						>
							<X class="size-4" />
						</Button>
					</div>
				</div>
			{/if}
		{/each}
	{/if}

	{#if supportsExtraFields && !only}
		{#if addingField && draftField}
			<div class="space-y-2 rounded-md border border-input bg-muted/30 p-3">
				<FieldKindRow
					field={draftField}
					labelSuggestions={fieldNameSuggestions(otherFields)}
					onLabelChange={nameDraft}
					onFieldChange={changeDraft}
				/>
				{#if joining}
					<p class="text-xs text-muted-foreground">
						Joins the {joining.label} detail on {joining.count === 1
							? '1 other item'
							: `${joining.count.toLocaleString('en-GB')} other items`}.
					</p>
				{/if}
				<div class="flex gap-2">
					<Button
						type="button"
						variant="outline"
						size="sm"
						onclick={confirmAddField}
						disabled={!draftField.label.trim()}
					>
						Add
					</Button>
					<Button type="button" variant="ghost" size="sm" onclick={cancelAddField}>Cancel</Button>
				</div>
			</div>
		{:else}
			<div class="flex flex-wrap gap-2">
				<Button
					type="button"
					variant="outline"
					size="sm"
					onclick={startAddField}
					disabled={extraFieldCount >= MAX_EXTRA_SCHEMA_FIELDS}
				>
					<Plus class="size-4" />
					Add field
				</Button>
				<Button
					type="button"
					variant="ghost"
					size="sm"
					onclick={() => (fieldSetPickerOpen = true)}
					disabled={extraFieldCount >= MAX_EXTRA_SCHEMA_FIELDS}
				>
					Add saved field group…
				</Button>
			</div>
			{#if extraFieldCount >= MAX_EXTRA_SCHEMA_FIELDS}
				<p class="text-xs text-muted-foreground">
					You can add up to {MAX_EXTRA_SCHEMA_FIELDS} extra fields.
				</p>
			{/if}
		{/if}
	{/if}
</div>

<BarcodeScanner
	bind:open={scannerOpen}
	onDetected={(code) => {
		if (scanKey !== null) setValue(scanKey, code);
	}}
/>

<PresetPickerDialog
	open={fieldSetPickerOpen}
	kind="field_set"
	title="Add saved field group"
	onOpenChange={(v) => (fieldSetPickerOpen = v)}
	onPick={addFieldSetFromPreset}
/>

<ConfirmDialog
	open={promoteAsk !== null}
	title={promoteAsk && nodeType ? `Make ${promoteAsk.label} a field of ${nodeType.label}?` : ''}
	description={promoteAsk
		? `It moves off this item and ${promoteAsk.others === 1 ? '1 other item' : `${promoteAsk.others.toLocaleString()} other items`}, which all keep their values.`
		: undefined}
	destructive={false}
	busy={promotingKey !== null}
	busyLabel="Adding…"
	confirmLabel="Make it a field"
	onOpenChange={(open) => {
		if (!open) promoteAsk = null;
	}}
	onConfirm={() => promoteAsk && void promoteField(promoteAsk.key)}
/>
