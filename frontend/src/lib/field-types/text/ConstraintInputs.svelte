<script lang="ts">
	import { Input } from '$lib/components/ui/input/index.js';
	import { readTextConfig } from './constraints';

	let {
		config,
		idPrefix,
		onChange
	}: {
		config: Record<string, unknown> | undefined;
		idPrefix: string;
		onChange: (config: Record<string, unknown>) => void;
	} = $props();

	let current = $derived(readTextConfig({ config }));

	function update(patch: { startsWith?: string; endsWith?: string }) {
		onChange({
			...config,
			startsWith: current.startsWith,
			endsWith: current.endsWith,
			...patch
		});
	}
</script>

{#if current.custom}
	<p class="text-xs text-muted-foreground">This field has a custom rule that is kept as it is.</p>
{:else}
	<div class="flex flex-wrap items-center gap-2">
		<label class="flex items-center gap-1.5 text-xs text-muted-foreground" for="{idPrefix}-starts">
			Starts with
			<Input
				id="{idPrefix}-starts"
				value={current.startsWith}
				placeholder="e.g. cover-"
				class="h-7 w-32 text-xs"
				oninput={(e) => update({ startsWith: (e.target as HTMLInputElement).value })}
			/>
		</label>
		<label class="flex items-center gap-1.5 text-xs text-muted-foreground" for="{idPrefix}-ends">
			Ends with
			<Input
				id="{idPrefix}-ends"
				value={current.endsWith}
				placeholder="e.g. .jpg"
				class="h-7 w-32 text-xs"
				oninput={(e) => update({ endsWith: (e.target as HTMLInputElement).value })}
			/>
		</label>
	</div>
{/if}
