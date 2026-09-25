<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { formatIsoDate } from '$lib/format-date';
	import { readPropMeta } from '$lib/schema-meta';
	import { getDescriptor } from '../registry';
	import { orderedColumns } from './columns';

	const VIEW_WIDGET_KINDS = new Set(['rating', 'quantity']);

	type GroupRow = Record<string, unknown>;

	let { value, prop }: { value: unknown; prop: JsonSchemaProperty } = $props();

	let rows = $derived(Array.isArray(value) ? (value as GroupRow[]) : []);
	let columns = $derived(orderedColumns(prop));

	function formatValue(val: unknown, sp: JsonSchemaProperty): string {
		if (val === null || val === undefined || val === '') return '—';
		if (sp.type === 'boolean') return val === true || val === 'true' ? 'Yes' : 'No';
		if (sp.type === 'string' && 'format' in sp && sp.format === 'date') {
			return formatIsoDate(val as string, 'short');
		}
		return String(val);
	}

	function isCompactColumn(sp: JsonSchemaProperty): boolean {
		if (sp.type === 'boolean') return true;
		if (sp.type === 'number') return true;
		if (sp.type === 'string' && 'format' in sp && sp.format === 'date') return true;
		const kind = readPropMeta(sp).kind;
		return kind === 'rating' || kind === 'quantity';
	}
</script>

{#if prop.type === 'array'}
	{#if rows.length > 0}
		<div class="flex-1 overflow-x-auto">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-input">
						{#each columns as [sk, sp] (sk)}
							<th
								class="px-2 py-1 text-left text-xs font-medium text-muted-foreground {isCompactColumn(
									sp
								)
									? 'w-px whitespace-nowrap'
									: ''}"
							>
								{sp.title || sk}
							</th>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each rows as row, ri (ri)}
						<tr class="border-b border-input/50 transition-colors last:border-0 hover:bg-muted/10">
							{#each columns as [sk, sp] (sk)}
								{@const kind = readPropMeta(sp).kind}
								{@const ViewWidget =
									kind && VIEW_WIDGET_KINDS.has(kind) ? getDescriptor(kind)?.ViewWidget : undefined}
								<td class="px-2 py-1 {isCompactColumn(sp) ? 'w-px whitespace-nowrap' : ''}">
									{#if ViewWidget}
										<ViewWidget value={row[sk]} prop={sp} />
									{:else}
										{formatValue(row[sk], sp)}
									{/if}
								</td>
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<span class="text-sm text-muted-foreground italic">No entries</span>
	{/if}
{/if}
