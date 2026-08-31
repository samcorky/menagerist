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

	// Keys defined in the schema
	let schemaKeys = $derived(schema?.fields.map((f) => f.key) ?? []);

	// Freeform rows: those not covered by the schema
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
	<Label>Attributes</Label>

	{#if schema && schema.fields.length > 0}
		<p class="text-xs text-muted-foreground">Schema fields</p>
		{#each schema.fields as field (field.key)}
			<div class="flex items-center gap-2">
				<span class="w-28 shrink-0 text-sm text-muted-foreground">
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
					<input
						type="checkbox"
						checked={getSchemaValue(field.key) === 'true'}
						onchange={(e) =>
							setSchemaValue(field.key, (e.target as HTMLInputElement).checked ? 'true' : 'false')}
						class="h-4 w-4 rounded border-input accent-primary"
						aria-label={field.label || field.key}
					/>
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

		{#if freeformRows.length > 0}
			<p class="pt-1 text-xs text-muted-foreground">Custom fields</p>
		{/if}
	{/if}

	{#each freeformRows as row (row)}
		<div class="flex gap-2">
			<Input bind:value={row.key} placeholder="Key" class="flex-1" aria-label="Attribute key" />
			<Input
				bind:value={row.value}
				placeholder="Value"
				class="flex-1"
				aria-label="Attribute value"
			/>
			<Button
				type="button"
				variant="ghost"
				size="icon"
				onclick={() => removeRow(row)}
				aria-label="Remove attribute"
			>
				<X class="size-4" />
			</Button>
		</div>
	{/each}

	<Button type="button" variant="outline" size="sm" onclick={addRow}>
		<Plus class="size-4" />
		Add attribute
	</Button>
</div>
