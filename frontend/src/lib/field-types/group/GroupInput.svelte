<script lang="ts">
	import { Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { descriptorForProp } from '../registry';
	import ScalarInput from '../ScalarInput.svelte';
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { readPropMeta } from '$lib/schema-meta';
	import { orderedColumns } from './columns';
	import { shouldMoveCell, nextCellPosition, type ArrowKey } from './keyboard-nav';

	type GroupRow = Record<string, unknown>;

	function compactColumnWidth(sp: JsonSchemaProperty): string | null {
		if (sp.type === 'boolean') return 'w-24';
		if (sp.type === 'number') return 'w-24';
		if (sp.type === 'string' && 'format' in sp && sp.format === 'date') return 'w-24';
		const kind = readPropMeta(sp).kind;
		if (kind === 'rating') return 'w-24';
		if (kind === 'quantity') return 'w-48';
		if (kind === 'money') return 'w-56';
		return null;
	}

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
	let columns = $derived(orderedColumns(prop));

	function addRow() {
		if (prop.type !== 'array' || prop.items.type !== 'object') return;
		const emptyRow = Object.fromEntries(Object.keys(prop.items.properties).map((k) => [k, '']));
		onChange([...rows, emptyRow]);
	}

	function removeRow(i: number) {
		onChange(rows.filter((_, ri) => ri !== i));
	}

	function setCell(rowIndex: number, key: string, val: unknown) {
		onChange(rows.map((row, i) => (i === rowIndex ? { ...row, [key]: val } : row)));
	}

	let tableEl = $state<HTMLTableElement | null>(null);

	function handleCellKeydown(e: KeyboardEvent, ri: number, ci: number) {
		const key = e.key;
		if (key !== 'ArrowUp' && key !== 'ArrowDown' && key !== 'ArrowLeft' && key !== 'ArrowRight')
			return;
		const target = e.target as HTMLInputElement;
		if (target.tagName !== 'INPUT' || target.type === 'checkbox' || target.type === 'radio') return;

		const caretPos = target.selectionStart ?? 0;
		const caret = { atStart: caretPos === 0, atEnd: caretPos === target.value.length };
		if (!shouldMoveCell(key as ArrowKey, caret)) return;

		const next = nextCellPosition(
			{ row: ri, col: ci },
			key as ArrowKey,
			rows.length,
			columns.length
		);
		if (!next) return;
		e.preventDefault();

		const nextCell = tableEl?.querySelector<HTMLElement>(
			`tbody tr:nth-child(${next.row + 1}) td:nth-child(${next.col + 1})`
		);
		nextCell?.querySelector<HTMLInputElement>('input')?.focus();
	}
</script>

{#if prop.type === 'array'}
	<div class="flex-1 space-y-2">
		<div class="overflow-x-auto rounded-md border border-input">
			<table class="w-full text-sm" bind:this={tableEl}>
				<thead>
					<tr class="border-b border-input bg-muted/50">
						{#each columns as [sk, sp] (sk)}
							<th
								class="px-2 py-1 text-left text-xs font-medium text-muted-foreground {compactColumnWidth(
									sp
								) ?? ''}"
							>
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
							{#each columns as [sk, sp], ci (sk)}
								{@const desc = descriptorForProp(sp)}
								{@const Widget = desc?.InputWidget ?? ScalarInput}
								<td class="px-1 py-0.5 {compactColumnWidth(sp) ?? ''}">
									<!-- svelte-ignore a11y_no_static_element_interactions -->
									<div
										class="[&_input]:h-7 [&_input]:border-transparent [&_input]:px-1.5 [&_input]:shadow-none [&_input]:focus-visible:ring-1"
										onkeydown={(e) => handleCellKeydown(e, ri, ci)}
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
