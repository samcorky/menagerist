<script lang="ts">
	import { TimeField as TimeFieldPrimitive } from 'bits-ui';
	import { Time } from '@internationalized/date';
	import { cn, type WithElementRef } from '$lib/utils.js';

	type Props = WithElementRef<
		Omit<TimeFieldPrimitive.InputProps, 'children' | 'child' | 'ref' | 'value'> & {
			/** 24-hour 'HH:MM' text, or null when empty. */
			value: string | null;
			/** Called with 'HH:MM' once a complete valid time is entered. */
			onValueChange: (value: string | null) => void;
			disabled?: boolean;
		},
		HTMLDivElement
	>;

	let {
		ref = $bindable(null),
		value,
		onValueChange,
		class: className,
		disabled = false,
		...restProps
	}: Props = $props();

	const match = $derived(value?.match(/^(\d{1,2}):(\d{2})$/) ?? null);
	const time = $derived(match ? new Time(Number(match[1]), Number(match[2])) : undefined);

	function pad(n: number): string {
		return String(n).padStart(2, '0');
	}
</script>

<TimeFieldPrimitive.Root
	value={time}
	onValueChange={(t) => onValueChange(t ? `${pad(t.hour)}:${pad(t.minute)}` : null)}
	hourCycle={24}
	granularity="minute"
	{disabled}
>
	<TimeFieldPrimitive.Input
		bind:ref
		data-slot="time-field"
		class={cn(
			'inline-flex h-11 w-fit items-center gap-0.5 rounded-2xl border border-transparent bg-input/50 px-3 py-1 text-base transition-[color,box-shadow] duration-200 outline-none focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30 aria-disabled:pointer-events-none aria-disabled:cursor-not-allowed aria-disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 data-[disabled]:pointer-events-none data-[disabled]:opacity-50 md:text-sm dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40',
			className
		)}
		{...restProps}
	>
		{#snippet children({ segments })}
			{#each segments as segment, i (i)}
				{#if segment.part === 'literal'}
					<TimeFieldPrimitive.Segment part={segment.part} class="text-muted-foreground">
						{segment.value}
					</TimeFieldPrimitive.Segment>
				{:else}
					<TimeFieldPrimitive.Segment
						part={segment.part}
						class="rounded px-0.5 tabular-nums outline-none focus:bg-accent focus:text-accent-foreground data-[placeholder]:text-muted-foreground"
					>
						{segment.value}
					</TimeFieldPrimitive.Segment>
				{/if}
			{/each}
		{/snippet}
	</TimeFieldPrimitive.Input>
</TimeFieldPrimitive.Root>
