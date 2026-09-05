<script lang="ts" module>
	export type AttributeRow = { key: string; value: string };

	/** Convert an API `attributes` dict into editable key/value rows. */
	export function attributesToRows(attributes: Record<string, unknown>): AttributeRow[] {
		return Object.entries(attributes).map(([key, value]) => ({ key, value: String(value) }));
	}

	/** Convert edited rows back into an `attributes` dict, dropping empty keys. */
	export function rowsToAttributes(rows: AttributeRow[]): Record<string, string> {
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
	import type { Schema } from './schema-editor.svelte';

	let { rows = $bindable(), schema = null }: { rows: AttributeRow[]; schema?: Schema | null } =
		$props();

	let schemaKeys = $derived(schema?.fields.map((f) => f.key) ?? []);
	let freeformRows = $derived(rows.filter((r) => !schemaKeys.includes(r.key)));

	function getSchemaValue(key: string): string {
		return rows.find((r) => r.key === key)?.value ?? '';
	}

	function setSchemaValue(key: string, value: string) {
		const existing = rows.find((r) => r.key === key);
		if (existing) {
			rows = rows.map((r) => (r.key === key ? { ...r, value } : r));
		} else {
			rows = [...rows, { key, value }];
		}
	}

	function addRow() {
		rows = [...rows, { key: '', value: '' }];
	}

	function removeRow(row: AttributeRow) {
		rows = rows.filter((existing) => existing !== row);
	}
</script>

<div class="space-y-2">
	<Label>Details</Label>

	{#if schema && schema.fields.length > 0}
		{#each schema.fields as field (field.key)}
			<div class="flex items-center gap-2">
				<span class="w-32 shrink-0 text-sm text-muted-foreground">
					{field.label || field.key}{#if field.required}<span class="ml-0.5 text-destructive"
							>*</span
						>{/if}
				</span>
				{#if field.type === 'number'}
					<Input
						type="number"
						value={getSchemaValue(field.key)}
						oninput={(e) => setSchemaValue(field.key, (e.target as HTMLInputElement).value)}
						class="flex-1"
						aria-label={field.label || field.key}
					/>
				{:else if field.type === 'boolean'}
					<label class="flex items-center gap-2">
						<input
							type="checkbox"
							checked={getSchemaValue(field.key) === 'true'}
							onchange={(e) =>
								setSchemaValue(
									field.key,
									(e.target as HTMLInputElement).checked ? 'true' : 'false'
								)}
							class="h-4 w-4 rounded border-input accent-primary"
							aria-label={field.label || field.key}
						/>
						<span class="sr-only">{field.label || field.key}</span>
					</label>
				{:else if field.type === 'date'}
					<Input
						type="date"
						value={getSchemaValue(field.key)}
						oninput={(e) => setSchemaValue(field.key, (e.target as HTMLInputElement).value)}
						class="flex-1"
						aria-label={field.label || field.key}
					/>
				{:else if field.type === 'select'}
					<select
						value={getSchemaValue(field.key)}
						onchange={(e) => setSchemaValue(field.key, (e.target as HTMLSelectElement).value)}
						class="h-9 flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
						aria-label={field.label || field.key}
					>
						<option value="">— select —</option>
						{#each field.options ?? [] as option (option)}
							<option value={option}>{option}</option>
						{/each}
					</select>
				{:else}
					<Input
						type="text"
						value={getSchemaValue(field.key)}
						oninput={(e) => setSchemaValue(field.key, (e.target as HTMLInputElement).value)}
						class="flex-1"
						aria-label={field.label || field.key}
					/>
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
							bind:value={row.value}
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
				<Input bind:value={row.value} placeholder="Value" class="flex-1" aria-label="Field value" />
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
