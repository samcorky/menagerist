<script lang="ts" module>
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

	/** Convert edited rows back into an `attributes` dict, dropping empty keys. */
	export function rowsToAttributes(rows: AttributeRow[]): Record<string, string | GroupRow[]> {
		return Object.fromEntries(
			rows.filter((row) => row.key.trim() !== '').map((row) => [row.key, row.value])
		);
	}
</script>

<script lang="ts">
	import { Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import type { Schema, SubField } from './schema-editor.svelte';

	let { rows = $bindable(), schema = null }: { rows: AttributeRow[]; schema?: Schema | null } =
		$props();

	let schemaKeys = $derived(schema?.fields.map((f) => f.key) ?? []);
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

	function addGroupRow(key: string, groupFields: SubField[]) {
		const emptyRow: GroupRow = Object.fromEntries(groupFields.map((f) => [f.key, '']));
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
</script>

{#snippet valueInput(
	type: SubField['type'],
	value: string,
	options: string[] | undefined,
	ariaLabel: string,
	onChange: (value: string) => void
)}
	{#if type === 'number'}
		<Input
			type="number"
			{value}
			oninput={(e) => onChange((e.target as HTMLInputElement).value)}
			class="flex-1"
			aria-label={ariaLabel}
		/>
	{:else if type === 'boolean'}
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
	{:else if type === 'date'}
		<Input
			type="date"
			{value}
			oninput={(e) => onChange((e.target as HTMLInputElement).value)}
			class="flex-1"
			aria-label={ariaLabel}
		/>
	{:else if type === 'select'}
		<select
			{value}
			onchange={(e) => onChange((e.target as HTMLSelectElement).value)}
			class="h-9 flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
			aria-label={ariaLabel}
		>
			<option value="">— select —</option>
			{#each options ?? [] as option (option)}
				<option value={option}>{option}</option>
			{/each}
		</select>
	{:else}
		<Input
			type="text"
			{value}
			oninput={(e) => onChange((e.target as HTMLInputElement).value)}
			class="flex-1"
			aria-label={ariaLabel}
		/>
	{/if}
{/snippet}

<div class="space-y-2">
	<Label>Details</Label>

	{#if schema && schema.fields.length > 0}
		{#each schema.fields as field (field.key)}
			<div class="flex gap-2 {field.type === 'group' ? 'items-start' : 'items-center'}">
				<span class="w-32 shrink-0 pt-1.5 text-sm text-muted-foreground">
					{field.label || field.key}{#if field.required}<span class="ml-0.5 text-destructive"
							>*</span
						>{/if}
				</span>
				{#if field.type === 'group'}
					<div class="flex-1 space-y-2">
						<div class="overflow-x-auto rounded-md border border-input">
							<table class="w-full text-sm">
								<thead>
									<tr class="border-b border-input bg-muted/50">
										{#each field.groupFields ?? [] as subField (subField.key)}
											<th class="px-2 py-1.5 text-left font-medium text-muted-foreground">
												{subField.label || subField.key}
											</th>
										{/each}
										<th class="w-9"></th>
									</tr>
								</thead>
								<tbody>
									{#each getGroupRows(field.key) as groupRow, ri (ri)}
										<tr class="border-b border-input last:border-0">
											{#each field.groupFields ?? [] as subField (subField.key)}
												<td class="px-2 py-1.5">
													{@render valueInput(
														subField.type,
														groupRow[subField.key] ?? '',
														subField.options,
														subField.label || subField.key,
														(value) => setGroupCellValue(field.key, ri, subField.key, value)
													)}
												</td>
											{/each}
											<td class="px-2 py-1.5 text-right">
												<Button
													type="button"
													variant="ghost"
													size="icon"
													onclick={() => removeGroupRow(field.key, ri)}
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
							onclick={() => addGroupRow(field.key, field.groupFields ?? [])}
						>
							<Plus class="size-4" />
							Add row
						</Button>
					</div>
				{:else}
					{@render valueInput(
						field.type,
						getSchemaValue(field.key),
						field.options,
						field.label || field.key,
						(value) => setSchemaValue(field.key, value)
					)}
				{/if}
			</div>
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
