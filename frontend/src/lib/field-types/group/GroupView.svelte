<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { formatIsoDate } from '$lib/format-date';

	type GroupRow = Record<string, unknown>;

	let { value, prop }: { value: unknown; prop: JsonSchemaProperty } = $props();

	let rows = $derived(Array.isArray(value) ? (value as GroupRow[]) : []);
	let columns = $derived(prop.type === 'array' ? Object.entries(prop.items.properties) : []);

	function formatValue(val: unknown, sp: JsonSchemaProperty): string {
		if (val === null || val === undefined || val === '') return '—';
		if (sp.type === 'boolean') return val === true || val === 'true' ? 'Yes' : 'No';
		if (sp.type === 'string' && 'format' in sp && sp.format === 'date') {
			return formatIsoDate(val as string, 'short');
		}
		return String(val);
	}
</script>

{#if prop.type === 'array'}
	{#if rows.length > 0}
		<div class="flex-1 overflow-x-auto">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-input">
						{#each columns as [sk, sp] (sk)}
							<th class="px-2 py-1 text-left text-xs font-medium text-muted-foreground">
								{sp.title || sk}
							</th>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each rows as row, ri (ri)}
						<tr class="border-b border-input/50 transition-colors last:border-0 hover:bg-muted/10">
							{#each columns as [sk, sp] (sk)}
								<td class="px-2 py-1">{formatValue(row[sk], sp)}</td>
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
