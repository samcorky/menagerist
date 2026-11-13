<script lang="ts">
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import BackLayer from '$lib/components/back-layer.svelte';

	let {
		open = $bindable(false),
		onOpenChange,
		children,
		...restProps
	}: DialogPrimitive.RootProps = $props();

	// The system Back gesture closes the dialog rather than leaving the page.
	function closeFromBack() {
		open = false;
		onOpenChange?.(false);
	}
</script>

<DialogPrimitive.Root bind:open {onOpenChange} {...restProps}>
	{@render children?.()}
	{#if open}
		<BackLayer onclose={closeFromBack} />
	{/if}
</DialogPrimitive.Root>
