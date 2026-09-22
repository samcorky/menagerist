<script lang="ts">
	import { Plus, X } from '@lucide/svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';
	import { rowsToAttributes } from '$lib/attribute-rows';
	import type { AttributeRow, GroupRow } from '$lib/attribute-rows';
	import type { AttributesSchema, JsonSchemaProperty, EditorField } from '$lib/schema-types';
	import { generateFieldKey } from '$lib/field-key';
	import { mergeAttributeSchemas, readSchemaMeta, validationSchema } from '$lib/schema-meta';
	import { isSection, schemaToItems, itemsToSchema } from '$lib/schema-editor-items';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { normalise, isSectionItem } from '$lib/layout';
	import { descriptorForProp } from '$lib/field-types';
	import { describeConstraints, parseConstraints } from '$lib/field-types/text/constraints';
	import { createSafeValidator } from '$lib/safe-validator';
	import { friendlyClientError, topLevelKey } from '$lib/validation-messages';
	import { promoteExtraSchemaField } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import FieldKindRow from '$lib/components/field-kind-row.svelte';

	/** Matches the backend's `MAX_EXTRA_SCHEMA_FIELDS` (extra_schema_limits.py). */
	const MAX_EXTRA_SCHEMA_FIELDS = 50;

	let {
		rows = $bindable(),
		schema = null,
		extraSchema = $bindable(null),
		supportsExtraFields = false,
		nodeId,
		nodeTypeId,
		onPromoted,
		serverErrors = null
	}: {
		rows: AttributeRow[];
		schema?: AttributesSchema | null;
		extraSchema?: AttributesSchema | null;
		supportsExtraFields?: boolean;
		nodeId?: string;
		nodeTypeId?: string;
		onPromoted?: () => void;
		serverErrors?: Record<string, string> | null;
	} = $props();

	let mergedSchema = $derived(mergeAttributeSchemas(schema, extraSchema));

	// Required is advisory and never blocks, so validate without it.
	let validator = $derived(
		mergedSchema
			? createSafeValidator(validationSchema($state.snapshot(mergedSchema)) as object)
			: null
	);

	const touched = new SvelteSet<string>();

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

	// -- Overlay field creation ("Add field") -----------------------------------

	let addingField = $state(false);
	let draftField = $state<EditorField | null>(null);

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
		addingField = true;
	}

	function cancelAddField() {
		addingField = false;
		draftField = null;
	}

	function confirmAddField() {
		if (!draftField || !draftField.label.trim()) return;
		const taken = [
			...Object.keys(schema?.properties ?? {}),
			...Object.keys(extraSchema?.properties ?? {})
		];
		const key = generateFieldKey(draftField.label, taken);
		const items = schemaToItems(extraSchema).filter((i): i is EditorField => !isSection(i));
		const nextItems = [...items, { ...draftField, key, keyPending: false }];
		extraSchema = itemsToSchema(nextItems, readSchemaMeta(extraSchema), []);
		rows = [...rows, { key, value: draftField.kind === 'boolean' ? 'false' : '' }];
		addingField = false;
		draftField = null;
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
		// PromoteExtraSchemaField) — build a real, empty schema instead so removing
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

	let promotingKey = $state<string | null>(null);

	async function promoteField(key: string) {
		if (!nodeId || !nodeTypeId) return;
		promotingKey = key;
		const result = await promoteExtraSchemaField({
			path: { node_id: nodeId, key },
			body: { node_type_id: nodeTypeId }
		});
		promotingKey = null;
		if (result.error) {
			toast.error("Couldn't make this a field", { description: errorMessage(result.error) });
			return;
		}
		toast.success('Field added to the item type');
		onPromoted?.();
	}
</script>

{#snippet fieldEntry(key: string, prop: JsonSchemaProperty)}
	{@const isRequired = requiredKeys.includes(key)}
	{@const error = fieldErrors[key]}
	{@const desc = descriptorForProp(prop)}
	{@const Widget = desc?.InputWidget}
	{@const parsed =
		prop.type === 'string'
			? parseConstraints(prop as { pattern?: unknown; allOf?: unknown })
			: null}
	{@const rule = parsed && !parsed.custom ? describeConstraints(parsed.constraints) : null}
	<div
		class="flex gap-2 {prop.type === 'array' ? 'items-start' : 'items-center'}"
		onfocusout={() => markTouched(key)}
	>
		<span class="w-32 shrink-0 pt-1.5 text-sm text-muted-foreground">
			{prop.title || key}{#if isRequired}{#if isEmptyValue(getValue(key))}<span
						class="ml-1 text-xs text-muted-foreground">Recommended</span
					>{:else}<span class="ml-0.5 text-muted-foreground">*</span>{/if}{/if}
		</span>
		<div class="flex flex-1 flex-col gap-1">
			{#if Widget}
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
				/>
			{/if}
			{#if error}
				<p class="text-xs text-destructive">{error}</p>
			{:else if rule}
				<p class="text-xs text-muted-foreground">{rule}</p>
			{/if}
		</div>
	</div>
{/snippet}

<div class="space-y-2">
	<Label>Details</Label>
	{#if validator?.degraded}
		<p class="text-xs text-muted-foreground" role="status">
			Some rules could not be checked here. They are still checked when you save.
		</p>
	{/if}

	{#if schema && schemaLayout.length > 0}
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

	{#if extraSchema && extraLayout.length > 0}
		{#each extraLayout as layoutItem (isSectionItem(layoutItem) ? layoutItem.id : layoutItem.key)}
			{#if !isSectionItem(layoutItem) && layoutItem.key in extraSchema.properties}
				{@const key = layoutItem.key}
				{@const prop = extraSchema.properties[key]}
				<div class="flex items-start gap-2">
					<div class="min-w-0 flex-1">
						{@render fieldEntry(key, prop)}
					</div>
					{#if supportsExtraFields && nodeId && nodeTypeId}
						<Button
							type="button"
							variant="ghost"
							size="sm"
							class="mt-1 h-7 text-xs"
							disabled={promotingKey === key}
							onclick={() => promoteField(key)}
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
			{/if}
		{/each}
	{/if}

	{#if supportsExtraFields}
		{#if addingField && draftField}
			<div class="space-y-2 rounded-md border border-input bg-muted/30 p-3">
				<FieldKindRow
					field={draftField}
					onLabelChange={(v) => (draftField = { ...draftField!, label: v })}
					onFieldChange={(f) => (draftField = f)}
				/>
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
			{#if extraFieldCount >= MAX_EXTRA_SCHEMA_FIELDS}
				<p class="text-xs text-muted-foreground">
					You can add up to {MAX_EXTRA_SCHEMA_FIELDS} extra fields.
				</p>
			{/if}
		{/if}
	{/if}
</div>
