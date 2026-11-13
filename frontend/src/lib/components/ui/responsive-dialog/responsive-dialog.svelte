<script lang="ts">
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import BackLayer from '$lib/components/back-layer.svelte';

	let {
		open = $bindable(false),
		onOpenChange,
		backLayer = true,
		children,
		...restProps
	}: DialogPrimitive.RootProps & {
		/**
		 * Whether the system Back gesture closes the dialog. Turn off for a dialog that manages
		 * its own history entries, such as the Filters panel, whose editing session is one entry.
		 */
		backLayer?: boolean;
	} = $props();

	// The system Back gesture closes the dialog rather than leaving the page.
	function closeFromBack() {
		open = false;
		onOpenChange?.(false);
	}
</script>

<DialogPrimitive.Root bind:open {onOpenChange} {...restProps}>
	{@render children?.()}
	{#if open && backLayer}
		<BackLayer onclose={closeFromBack} />
	{/if}
</DialogPrimitive.Root>
