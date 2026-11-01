<script lang="ts">
	import * as Tooltip from '$lib/components/ui/popover-tooltip/index.js';
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { moneyCurrencyName, moneyText } from './format';

	let { value, prop: _prop }: { value: unknown; prop: JsonSchemaProperty } = $props();
	let currencyName = $derived(moneyCurrencyName(value));
</script>

{#if currencyName}
	<Tooltip.Root>
		<Tooltip.Trigger>
			{#snippet child({ props })}
				<button
					{...props}
					type="button"
					class="cursor-help appearance-none border-0 bg-transparent p-0 text-inherit underline decoration-dotted underline-offset-2"
					style="font: inherit"
				>
					{moneyText(value) || '-'}
				</button>
			{/snippet}
		</Tooltip.Trigger>
		<Tooltip.Content>{currencyName}</Tooltip.Content>
	</Tooltip.Root>
{:else}
	<span>{moneyText(value) || '-'}</span>
{/if}
