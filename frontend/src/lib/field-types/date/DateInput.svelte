<script lang="ts">
	import { ChevronDown } from '@lucide/svelte';
	import {
		CalendarDate,
		parseDate,
		getLocalTimeZone,
		type DateValue
	} from '@internationalized/date';
	import * as Popover from '$lib/components/ui/popover/index.js';
	import Calendar from '$lib/components/ui/calendar/calendar.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { cn } from '$lib/utils.js';
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let {
		value,
		onChange,
		ariaLabel,
		prop: _prop
	}: {
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	} = $props();

	let open = $state(false);

	let calValue = $derived.by((): CalendarDate | undefined => {
		if (typeof value !== 'string' || value === '') return undefined;
		try {
			return parseDate(value);
		} catch {
			return undefined;
		}
	});

	function handleValueChange(newVal: DateValue | undefined) {
		onChange(newVal?.toString() ?? '');
		open = false;
	}
</script>

<Popover.Root bind:open>
	<Popover.Trigger>
		{#snippet child({ props })}
			<Button
				{...props}
				variant="outline"
				class={cn('w-full justify-start font-normal', !calValue && '!text-muted-foreground')}
				aria-label={ariaLabel}
			>
				{#if calValue}
					{calValue.toDate(getLocalTimeZone()).toLocaleDateString()}
				{:else}
					Select a date
				{/if}
				<ChevronDown class="ml-auto size-4 opacity-50" />
			</Button>
		{/snippet}
	</Popover.Trigger>
	<Popover.Content class="w-auto p-0" align="start">
		<Calendar
			type="single"
			value={calValue}
			onValueChange={handleValueChange}
			captionLayout="dropdown"
		/>
	</Popover.Content>
</Popover.Root>
