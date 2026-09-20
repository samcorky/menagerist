<script lang="ts">
	import { Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { descriptorForProp } from '../registry';
	import ScalarInput from '../ScalarInput.svelte';
	import type { JsonSchemaProperty } from '$lib/schema-types';

	type GroupRow = Record<string, unknown>;

	let {
		value,
		onChange,
		ariaLabel: _ariaLabel,
		prop
	}: {
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	} = $props();

	let rows = $derived(Array.isArray(value) ? (value as GroupRow[]) : []);
	let columns = $derived(prop.type === 'array' ? Object.entries(prop.items.properties) : []);

	function addRow() {
		if (prop.type !== 'array') return;
		const emptyRow = Object.fromEntries(Object.keys(prop.items.properties).map((k) => [k, '']));
		onChange([...rows, emptyRow]);
	}

	function removeRow(i: number) {
		onChange(rows.filter((_, ri) => ri !== i));
	}

	function setCell(rowIndex: number, key: string, val: unknown) {
		onChange(rows.map((row, i) => (i === rowIndex ? { ...row, [key]: val } : row)));
	}
</script>

{#if prop.type === 'array'}
	<div class="flex-1 space-y-2">
		<div class="overflow-x-auto rounded-md border border-input">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-input bg-muted/50">
						{#each columns as [sk, sp] (sk)}
							<th class="px-2 py-1 text-left text-xs font-medium text-muted-foreground">
								{sp.title || sk}
							</th>
						{/each}
						<th class="w-9"></th>
					</tr>
				</thead>
				<tbody>
					{#if rows.length === 0}
						<tr>
							<td colspan={columns.length + 1}>
								<p class="py-3 text-center text-xs text-muted-foreground">No entries yet</p>
							</td>
						</tr>
					{/if}
					{#each rows as row, ri (ri)}
						<tr class="border-b border-input transition-colors last:border-0 hover:bg-muted/30">
							{#each columns as [sk, sp] (sk)}
								{@const desc = descriptorForProp(sp)}
								{@const Widget = desc?.InputWidget ?? ScalarInput}
								<td class="px-1 py-0.5">
									<div
										class="[&_input]:h-7 [&_input]:border-transparent [&_input]:bg-transparent [&_input]:px-1.5 [&_input]:shadow-none [&_input]:focus-visible:ring-1"
									>
										<Widget
											value={row[sk] ?? ''}
											onChange={(v) => setCell(ri, sk, v)}
											ariaLabel={sp.title || sk}
											prop={sp}
										/>
									</div>
								</td>
							{/each}
							<td class="px-1 py-0.5 text-right">
								<Button
									type="button"
									variant="ghost"
									class="size-7"
									onclick={() => removeRow(ri)}
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
		<Button type="button" variant="outline" size="sm" onclick={addRow}>
			<Plus class="size-4" />
			Add row
		</Button>
	</div>
{/if}
