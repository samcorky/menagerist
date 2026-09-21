<script lang="ts" module>
	import type { AttributesSchema, JsonSchemaProperty } from '$lib/schema-types';
	import { archivedKeys, readSchemaMeta, validationSchema } from '$lib/schema-meta';

	export type GroupRow = Record<string, string>;
	export type AttributeRow = { key: string; value: string | GroupRow[] };

	function isGroupValue(value: unknown): value is Record<string, unknown>[] {
		return (
			Array.isArray(value) &&
			value.every((v) => typeof v === 'object' && v !== null && !Array.isArray(v))
		);
	}

	/** Convert an API `attributes` dict into editable key/value rows. */
	export function attributesToRows(attributes: Record<string, unknown>): AttributeRow[] {
		return Object.entries(attributes).map(([key, value]) => {
			if (isGroupValue(value)) {
				return {
					key,
					value: value.map((entry) =>
						Object.fromEntries(Object.entries(entry).map(([k, v]) => [k, String(v)]))
					)
				};
			}
			return { key, value: String(value) };
		});
	}

	function isOmittedWhenEmpty(prop: JsonSchemaProperty | undefined): boolean {
		if (!prop) return false;
		if (prop.type === 'number') return true;
		if (prop.type !== 'string') return false;
		// An empty string fails an anchored pattern, so an empty constrained text field is omitted.
		const p = prop as { pattern?: unknown; allOf?: unknown };
		return (
			'enum' in prop ||
			('format' in prop && prop.format === 'date') ||
			p.pattern !== undefined ||
			p.allOf !== undefined
		);
	}

	function coerceScalar(value: string, prop: JsonSchemaProperty | undefined): unknown {
		if (prop?.type === 'number') {
			const n = Number(value);
			return isNaN(n) ? value : n;
		}
		// An untouched checkbox has no unset state, so '' becomes false.
		if (prop?.type === 'boolean') return value === 'true';
		return value;
	}

	/**
	 * Convert edited rows into a typed `attributes` dict ready for the API.
	 * Pass `schema` so number/boolean fields are emitted as real JS types.
	 * Empty number, date and enum values are omitted rather than sent as empty strings.
	 */
	export function rowsToAttributes(
		rows: AttributeRow[],
		schema?: AttributesSchema | null
	): Record<string, unknown> {
		const props = schema?.properties ?? {};
		return Object.fromEntries(
			rows
				.filter((row) => row.key.trim() !== '')
				.flatMap((row): [string, unknown][] => {
					const prop = props[row.key];
					if (typeof row.value !== 'string') {
						if (prop?.type === 'array' && prop.items?.type === 'object') {
							const subProps = prop.items.properties ?? {};
							return [
								[
									row.key,
									row.value.map((gr) =>
										Object.fromEntries(
											Object.entries(gr)
												.filter(([k, v]) => !(v === '' && isOmittedWhenEmpty(subProps[k])))
												.map(([k, v]) => [k, coerceScalar(v, subProps[k])])
										)
									)
								]
							];
						}
						return [[row.key, row.value]];
					}
					if (row.value === '' && isOmittedWhenEmpty(prop)) return [];
					if (prop?.type === 'number') {
						if (row.value === '') return [];
						const n = Number(row.value);
						return isNaN(n) ? [[row.key, row.value]] : [[row.key, n]];
					}
					// An empty top-level boolean means "not recorded", not false.
					if (prop?.type === 'boolean' && row.value === '') return [];
					if (prop?.type === 'boolean') return [[row.key, row.value === 'true']];
					return [[row.key, row.value]];
				})
		);
	}
</script>

<script lang="ts">
	import { Plus, X } from '@lucide/svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { normalise, orderedKeys, isSectionItem } from '$lib/layout';
	import { descriptorForProp } from '$lib/field-types';
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
	let schemaKeys = $derived(orderedKeys(schemaLayout));
	let hiddenKeys = $derived(archivedKeys(schema));
	let freeformRows = $derived(
		rows.filter((r) => !schemaKeys.includes(r.key) && !hiddenKeys.has(r.key))
	);

	function getValue(key: string): unknown {
		return rows.find((r) => r.key === key)?.value ?? '';
	}

	function setValue(key: string, value: unknown) {
		const existing = rows.find((r) => r.key === key);
		if (existing) {
			rows = rows.map((r) => (r.key === key ? { ...r, value: value as string | GroupRow[] } : r));
		} else {
			rows = [...rows, { key, value: value as string | GroupRow[] }];
		}
	}

	function addRow() {
		rows = [...rows, { key: '', value: '' }];
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
			{prop.title || key}{#if isRequired}<span class="ml-0.5 text-destructive">*</span>{/if}
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

		<!-- Custom fields: collapsible when schema fields exist -->
		<details open={freeformRows.length > 0} class="pt-1">
			<summary
				class="cursor-pointer text-xs text-muted-foreground select-none hover:text-foreground"
			>
				Additional details{freeformRows.length > 0 ? ` (${freeformRows.length})` : ''}
			</summary>
			<div class="mt-2 space-y-2">
				{#each freeformRows as row (row)}
					<div class="flex gap-2">
						<Input
							bind:value={row.key}
							placeholder="Field name"
							class="flex-1"
							aria-label="Field name"
						/>
						<Input
							value={typeof row.value === 'string' ? row.value : ''}
							oninput={(e) => (row.value = (e.target as HTMLInputElement).value)}
							placeholder="Value"
							class="flex-1"
							aria-label="Field value"
						/>
						<Button
							type="button"
							variant="ghost"
							size="icon"
							onclick={() => removeRow(row)}
							aria-label="Remove field"
						>
							<X class="size-4" />
						</Button>
					</div>
				{/each}
				<Button type="button" variant="outline" size="sm" onclick={addRow}>
					<Plus class="size-4" />
					Add detail
				</Button>
			</div>
		</details>
	{:else}
		<!-- No schema: show freeform fields flat -->
		{#each freeformRows as row (row)}
			<div class="flex gap-2">
				<Input
					bind:value={row.key}
					placeholder="Field name"
					class="flex-1"
					aria-label="Field name"
				/>
				<Input
					value={typeof row.value === 'string' ? row.value : ''}
					oninput={(e) => (row.value = (e.target as HTMLInputElement).value)}
					placeholder="Value"
					class="flex-1"
					aria-label="Field value"
				/>
				<Button
					type="button"
					variant="ghost"
					size="icon"
					onclick={() => removeRow(row)}
					aria-label="Remove field"
				>
					<X class="size-4" />
				</Button>
			</div>
		{/each}

		<Button type="button" variant="outline" size="sm" onclick={addRow}>
			<Plus class="size-4" />
			Add detail
		</Button>
	{/if}
</div>
