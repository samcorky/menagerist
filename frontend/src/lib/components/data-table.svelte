<script lang="ts" module>
	export interface DataTableColumn {
		label: string;
		/** Right-align the column, for row actions. */
		end?: boolean;
	}
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import * as Table from '$lib/components/ui/table/index.js';

	let {
		label,
		columns,
		children
	}: {
		/** Accessible name of the table. */
		label: string;
		columns: DataTableColumn[];
		/** The `<Table.Row>`s of the body. */
		children: Snippet;
	} = $props();
</script>

<!-- The desktop counterpart of a card list; pair it with `wide` from `$lib/viewport.svelte`. -->
<div class="overflow-hidden rounded-xl border bg-card">
	<Table.Root
		aria-label={label}
		class="text-left [&_td]:px-4 [&_td]:py-2 [&_td]:align-top [&_td]:whitespace-normal"
	>
		<Table.Header class="bg-muted/40">
			<Table.Row class="hover:bg-transparent">
				{#each columns as column (column.label)}
					<Table.Head
						scope="col"
						class="h-auto px-4 py-2 text-xs font-medium text-muted-foreground uppercase {column.end
							? 'text-right'
							: ''}">{column.label}</Table.Head
					>
				{/each}
			</Table.Row>
		</Table.Header>
		<Table.Body>
			{@render children()}
		</Table.Body>
	</Table.Root>
</div>
