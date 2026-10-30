<script lang="ts">
	import { Eye, EyeOff } from '@lucide/svelte';
	import * as InputGroup from '$lib/components/ui/input-group/index.js';
	import { cn } from '$lib/utils.js';
	import type { ComponentProps } from 'svelte';

	let {
		ref = $bindable(null),
		value = $bindable(''),
		class: className,
		disabled,
		...restProps
	}: Omit<ComponentProps<typeof InputGroup.Input>, 'type' | 'files'> = $props();

	// Resets on remount, so closing a dialog or leaving the page hides it again.
	let visible = $state(false);
</script>

<InputGroup.Root
	class={cn('pointer-coarse:h-11', className)}
	data-disabled={disabled ? 'true' : undefined}
>
	<InputGroup.Input
		bind:ref
		bind:value
		{...restProps}
		{disabled}
		type={visible ? 'text' : 'password'}
		class="h-full"
	/>
	<InputGroup.Addon align="inline-end">
		<InputGroup.Button
			size="icon-sm"
			class="pointer-coarse:size-11"
			{disabled}
			aria-label={visible ? 'Hide password' : 'Show password'}
			aria-pressed={visible}
			onmousedown={(e) => e.preventDefault()}
			onclick={() => (visible = !visible)}
		>
			{#if visible}
				<EyeOff class="size-4" />
			{:else}
				<Eye class="size-4" />
			{/if}
		</InputGroup.Button>
	</InputGroup.Addon>
</InputGroup.Root>
