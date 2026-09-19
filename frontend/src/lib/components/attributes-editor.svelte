<script lang="ts" module>
	import type { AttributesSchema, JsonSchemaProperty } from './schema-editor.svelte';

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
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import { normalise, orderedKeys, isSectionItem } from '$lib/layout';

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

	function getSchemaValue(key: string): string {
		const value = rows.find((r) => r.key === key)?.value;
		return typeof value === 'string' ? value : '';
	}

	function setSchemaValue(key: string, value: string) {
		const existing = rows.find((r) => r.key === key);
		if (existing) {
			rows = rows.map((r) => (r.key === key ? { ...r, value } : r));
		} else {
			rows = [...rows, { key, value }];
		}
	}

	function getGroupRows(key: string): GroupRow[] {
		const value = rows.find((r) => r.key === key)?.value;
		return Array.isArray(value) ? value : [];
	}

	function setGroupRows(key: string, groupRows: GroupRow[]) {
		const existing = rows.find((r) => r.key === key);
		if (existing) {
			rows = rows.map((r) => (r.key === key ? { ...r, value: groupRows } : r));
		} else {
			rows = [...rows, { key, value: groupRows }];
		}
	}

	function setGroupCellValue(key: string, rowIndex: number, subKey: string, value: string) {
		setGroupRows(
			key,
			getGroupRows(key).map((row, i) => (i === rowIndex ? { ...row, [subKey]: value } : row))
		);
	}

	function addGroupRow(key: string, subProps: Record<string, JsonSchemaProperty>) {
		const emptyRow: GroupRow = Object.fromEntries(Object.keys(subProps).map((k) => [k, '']));
		setGroupRows(key, [...getGroupRows(key), emptyRow]);
	}

	function removeGroupRow(key: string, rowIndex: number) {
		setGroupRows(
			key,
			getGroupRows(key).filter((_, i) => i !== rowIndex)
		);
	}

	function addRow() {
		rows = [...rows, { key: '', value: '' }];
	}

	function removeRow(row: AttributeRow) {
		rows = rows.filter((existing) => existing !== row);
	}

	function inputType(prop: JsonSchemaProperty): string {
		if (prop.type === 'number') return 'number';
		if ('format' in prop && prop.format === 'date') return 'date';
		return 'text';
	}
</script>

{#snippet valueInput(
	prop: JsonSchemaProperty,
	value: string,
	ariaLabel: string,
	onChange: (value: string) => void
)}
	{#if prop.type === 'boolean'}
		<label class="flex items-center gap-2">
			<input
				type="checkbox"
				checked={value === 'true'}
				onchange={(e) => onChange((e.target as HTMLInputElement).checked ? 'true' : 'false')}
				class="h-4 w-4 rounded border-input accent-primary"
				aria-label={ariaLabel}
			/>
			<span class="sr-only">{ariaLabel}</span>
		</label>
	{:else if prop.type === 'string' && 'enum' in prop}
		<select
			{value}
			onchange={(e) => onChange((e.target as HTMLSelectElement).value)}
			class="h-9 flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
			aria-label={ariaLabel}
		>
			<option value="">— select —</option>
			{#each prop.enum as option (option)}
				<option value={option}>{option}</option>
			{/each}
		</select>
	{:else if prop.type === 'string' && 'x-multiline' in prop && prop['x-multiline']}
		<Textarea
			{value}
			oninput={(e) => onChange((e.target as HTMLTextAreaElement).value)}
			class="flex-1"
			aria-label={ariaLabel}
		/>
	{:else}
		<Input
			type={inputType(prop)}
			{value}
			oninput={(e) => onChange((e.target as HTMLInputElement).value)}
			class="flex-1"
			aria-label={ariaLabel}
		/>
	{/if}
{/snippet}

<div class="space-y-2">
	<Label>Details</Label>

	{#snippet fieldEntry(key: string, prop: JsonSchemaProperty)}
		{@const isRequired = schema?.required?.includes(key) ?? false}
		{@const error = fieldErrors[key]}
		<div class="flex gap-2 {prop.type === 'array' ? 'items-start' : 'items-center'}">
			<span class="w-32 shrink-0 pt-1.5 text-sm text-muted-foreground">
				{prop.title || key}{#if isRequired}<span class="ml-0.5 text-destructive">*</span>{/if}
			</span>
			{#if prop.type === 'array'}
				<div class="flex-1 space-y-2">
					<div class="overflow-x-auto rounded-md border border-input">
						<table class="w-full text-sm">
							<thead>
								<tr class="border-b border-input bg-muted/50">
									{#each Object.entries(prop.items.properties) as [sk, sp] (sk)}
										<th class="px-2 py-1.5 text-left font-medium text-muted-foreground">
											{sp.title || sk}
										</th>
									{/each}
									<th class="w-9"></th>
								</tr>
							</thead>
							<tbody>
								{#each getGroupRows(key) as groupRow, ri (ri)}
									<tr class="border-b border-input last:border-0">
										{#each Object.entries(prop.items.properties) as [sk, sp] (sk)}
											<td class="px-2 py-1.5">
												{@render valueInput(sp, groupRow[sk] ?? '', sp.title || sk, (value) =>
													setGroupCellValue(key, ri, sk, value)
												)}
											</td>
										{/each}
										<td class="px-2 py-1.5 text-right">
											<Button
												type="button"
												variant="ghost"
												size="icon"
												onclick={() => removeGroupRow(key, ri)}
												aria-label="Remove row"
											>
												<X class="size-4" />
											</Button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<Button
						type="button"
						variant="outline"
						size="sm"
						onclick={() => addGroupRow(key, prop.items.properties)}
					>
						<Plus class="size-4" />
						Add row
					</Button>
				</div>
			{:else}
				<div class="flex flex-1 flex-col gap-1">
					{@render valueInput(prop, getSchemaValue(key), prop.title || key, (value) =>
						setSchemaValue(key, value)
					)}
					{#if error}
						<p class="text-xs text-destructive">{error}</p>
					{/if}
				</div>
			{/if}
		</div>
	{/snippet}

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
