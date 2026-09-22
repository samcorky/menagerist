<script lang="ts">
	import { Plus, X } from '@lucide/svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { newDetailRow, rowsToAttributes } from '$lib/attribute-rows';
	import type { AttributeRow, GroupRow } from '$lib/attribute-rows';
	import type { AttributesSchema, JsonSchemaProperty } from '$lib/schema-types';
	import { readSchemaMeta, validationSchema } from '$lib/schema-meta';
	import {
		MAX_CUSTOM_DETAILS,
		canAddDetail,
		customDetailProblems,
		displayDetailValue,
		isDetailRow
	} from '$lib/custom-details';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { normalise, isSectionItem } from '$lib/layout';
	import { descriptorForProp, getDescriptor } from '$lib/field-types';
	import { describeConstraints, parseConstraints } from '$lib/field-types/text/constraints';
	import { createSafeValidator } from '$lib/safe-validator';
	import { friendlyClientError, topLevelKey } from '$lib/validation-messages';

	let {
		rows = $bindable(),
		schema = null,
		serverErrors = null
	}: {
		rows: AttributeRow[];
		schema?: AttributesSchema | null;
		serverErrors?: Record<string, string> | null;
	} = $props();

	// Required is advisory and never blocks, so validate without it.
	let validator = $derived(
		schema ? createSafeValidator(validationSchema($state.snapshot(schema)) as object) : null
	);

	const touched = new SvelteSet<string>();

	let clientErrors = $derived.by(() => {
		const errors: Record<string, string> = {};
		if (!validator || !schema) return errors;
		for (const err of validator.validate(rowsToAttributes(rows, schema))) {
			const key = topLevelKey(err.instanceLocation);
			if (key && !errors[key]) errors[key] = friendlyClientError(schema, err);
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

	let schemaMeta = $derived(schema ? readSchemaMeta(schema) : null);
	let requiredKeys = $derived(schemaMeta?.required ?? []);
	let schemaLayout = $derived(schema ? normalise(schemaMeta?.layout, schema.properties) : []);
	let freeformRows = $derived(rows.filter((r) => isDetailRow(r, schema)));
	let problems = $derived(customDetailProblems(rows, schema));

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

	function addRow() {
		rows = [...rows, newDetailRow()];
	}

	function setKind(row: AttributeRow, kind: string) {
		row.kind = kind as 'text' | 'number' | 'boolean';
		row.value = kind === 'boolean' ? 'false' : '';
	}

	function removeRow(row: AttributeRow) {
		rows = rows.filter((existing) => existing !== row);
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

{#snippet detailRow(row: AttributeRow)}
	{@const NumberWidget = getDescriptor('number')?.InputWidget}
	{@const BooleanWidget = getDescriptor('boolean')?.InputWidget}
	{@const error = problems.errors.get(row) ?? serverErrors?.[row.key.trim()]}
	<div class="space-y-1">
		<div class="flex items-center gap-2">
			<Input
				bind:value={row.key}
				placeholder="Detail name"
				class="flex-1"
				aria-label="Detail name"
			/>
			{#if row.extra}
				<select
					value={row.kind ?? 'text'}
					onchange={(e) => setKind(row, (e.target as HTMLSelectElement).value)}
					class="h-9 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
					aria-label="Value type"
				>
					<option value="text">Text</option>
					<option value="number">Number</option>
					<option value="boolean">Yes/No</option>
				</select>
			{/if}
			{#if row.kind === 'number' && NumberWidget}
				<NumberWidget
					value={typeof row.value === 'string' ? row.value : ''}
					onChange={(v) => (row.value = String(v))}
					ariaLabel="Detail value"
					prop={{ title: 'Value', type: 'number' }}
				/>
			{:else if row.kind === 'boolean' && BooleanWidget}
				<div class="flex flex-1 items-center">
					<BooleanWidget
						value={typeof row.value === 'string' ? row.value : ''}
						onChange={(v) => (row.value = String(v))}
						ariaLabel="Detail value"
						prop={{ title: 'Value', type: 'boolean' }}
					/>
				</div>
			{:else if row.kind === 'json'}
				<code
					class="min-w-0 flex-1 truncate rounded bg-muted px-2 py-1 text-xs"
					title={displayDetailValue(row)}>{displayDetailValue(row)}</code
				>
			{:else}
				<Input
					value={typeof row.value === 'string' ? row.value : ''}
					oninput={(e) => (row.value = (e.target as HTMLInputElement).value)}
					placeholder="Value"
					class="flex-1"
					aria-label="Detail value"
				/>
			{/if}
			<Button
				type="button"
				variant="ghost"
				size="icon"
				onclick={() => removeRow(row)}
				aria-label="Remove detail"
			>
				<X class="size-4" />
			</Button>
		</div>
		{#if error}
			<p class="text-xs text-destructive">{error}</p>
		{/if}
	</div>
{/snippet}

{#snippet addDetailButton()}
	<Button
		type="button"
		variant="outline"
		size="sm"
		onclick={addRow}
		disabled={!canAddDetail(rows, schema)}
	>
		<Plus class="size-4" />
		Add detail
	</Button>
	{#if !canAddDetail(rows, schema)}
		<p class="text-xs text-muted-foreground">
			You can add up to {MAX_CUSTOM_DETAILS} extra details.
		</p>
	{/if}
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

		<!-- Custom fields: collapsible when schema fields exist -->
		<details open={freeformRows.length > 0} class="pt-1">
			<summary
				class="cursor-pointer text-xs text-muted-foreground select-none hover:text-foreground"
			>
				Additional details{freeformRows.length > 0 ? ` (${freeformRows.length})` : ''}
			</summary>
			<div class="mt-2 space-y-2">
				{#each freeformRows as row (row)}
					{@render detailRow(row)}
				{/each}
				{@render addDetailButton()}
			</div>
		</details>
	{:else}
		<!-- No schema: show freeform fields flat -->
		{#each freeformRows as row (row)}
			{@render detailRow(row)}
		{/each}
		{@render addDetailButton()}
	{/if}
</div>
