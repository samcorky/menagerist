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

	let { rows = $bindable() }: { rows: AttributeRow[] } = $props();

	function addRow() {
		rows = [...rows, { key: '', value: '' }];
	}

	function removeRow(row: AttributeRow) {
		rows = rows.filter((existing) => existing !== row);
	}
</script>

<div class="space-y-2">
	<Label>Attributes</Label>

	{#each rows as row (row)}
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
