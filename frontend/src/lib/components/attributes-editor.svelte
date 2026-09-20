<script lang="ts" module>
	import type { AttributesSchema, JsonSchemaProperty } from '$lib/schema-types';

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

	function coerceScalar(value: string, prop: JsonSchemaProperty | undefined): unknown {
		if (prop?.type === 'number') {
			const n = Number(value);
			return isNaN(n) ? value : n;
		}
		if (prop?.type === 'boolean') return value === 'true';
		return value;
	}

	/**
	 * Convert edited rows into a typed `attributes` dict ready for the API.
	 * Pass `schema` so number/boolean fields are emitted as real JS types.
	 * Empty number fields are omitted rather than sent as empty strings.
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
						if (prop?.type === 'array') {
							const subProps = prop.items.properties;
							return [
								[
									row.key,
									row.value.map((gr) =>
										Object.fromEntries(
											Object.entries(gr).map(([k, v]) => [k, coerceScalar(v, subProps[k])])
										)
									)
								]
							];
						}
						return [[row.key, row.value]];
					}
					if (prop?.type === 'number') {
						if (row.value === '') return [];
						const n = Number(row.value);
						return isNaN(n) ? [[row.key, row.value]] : [[row.key, n]];
					}
					if (prop?.type === 'boolean') return [[row.key, row.value === 'true']];
					return [[row.key, row.value]];
				})
		);
	}
</script>

<script lang="ts">
	import { Validator } from '@cfworker/json-schema';
	import { Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { normalise, orderedKeys, isSectionItem } from '$lib/layout';
	import { descriptorForProp } from '$lib/field-types';

	let {
		rows = $bindable(),
		schema = null,
		serverErrors = null
	}: {
		rows: AttributeRow[];
		schema?: AttributesSchema | null;
		serverErrors?: Record<string, string> | null;
	} = $props();

	let validator = $derived(
		schema ? new Validator($state.snapshot(schema) as object, '2020-12', false) : null
	);

	let fieldErrors = $derived.by(() => {
		const errors: Record<string, string> = { ...serverErrors };
		if (!validator || !schema) return errors;
		const attrs = rowsToAttributes(rows, schema);
		const result = validator.validate(attrs);
		for (const err of result.errors) {
			const key = err.instanceLocation.replace(/^#\/?/, '');
			if (key && !errors[key]) errors[key] = err.error ?? 'Invalid value';
		}
		return errors;
	});

	let schemaLayout = $derived(schema ? normalise(schema['x-layout'], schema.properties) : []);
	let schemaKeys = $derived(orderedKeys(schemaLayout));
	let freeformRows = $derived(rows.filter((r) => !schemaKeys.includes(r.key)));

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
	{@const isRequired = schema?.required?.includes(key) ?? false}
	{@const error = fieldErrors[key]}
	{@const desc = descriptorForProp(prop)}
	{@const Widget = desc?.InputWidget}
	<div class="flex gap-2 {prop.type === 'array' ? 'items-start' : 'items-center'}">
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
			{/if}
		</div>
	</div>
{/snippet}

<div class="space-y-2">
	<Label>Details</Label>

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
