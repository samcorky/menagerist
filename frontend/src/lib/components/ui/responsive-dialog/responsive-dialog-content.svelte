<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	/**
	 * A bottom sheet on mobile (drag handle, slides up from the bottom edge) that becomes a
	 * centered dialog at the `sm` breakpoint — the app's one modal shape, per DESIGN_GUIDELINES §23.
	 */
	export const responsiveDialogContentVariants = tv({
		base: 'fixed right-0 bottom-0 left-0 z-50 max-h-[90dvh] overflow-y-auto rounded-t-2xl border-t bg-background p-6 shadow-xl sm:inset-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-full sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border',
		variants: {
			size: {
				sm: 'sm:max-w-sm',
				md: 'sm:max-w-md',
				lg: 'sm:max-w-lg'
			}
		},
		defaultVariants: {
			size: 'md'
		}
	});

	export type ResponsiveDialogContentSize = VariantProps<
		typeof responsiveDialogContentVariants
	>['size'];
</script>

<script lang="ts">
	import { Dialog as DialogPrimitive } from 'bits-ui';
	import { X } from '@lucide/svelte';
	import { cn, type WithoutChildrenOrChild } from '$lib/utils.js';
	import type { ComponentProps } from 'svelte';
	import ResponsiveDialogPortal from './responsive-dialog-portal.svelte';
	import ResponsiveDialogOverlay from './responsive-dialog-overlay.svelte';

	let {
		ref = $bindable(null),
		class: className,
		size = 'md',
		title,
		portalProps,
		overlayProps,
		children,
		...restProps
	}: DialogPrimitive.ContentProps & {
		size?: ResponsiveDialogContentSize;
		/** Rendered as the dialog's heading, and its accessible name. */
		title: string;
		portalProps?: WithoutChildrenOrChild<ComponentProps<typeof ResponsiveDialogPortal>>;
		overlayProps?: WithoutChildrenOrChild<ComponentProps<typeof ResponsiveDialogOverlay>>;
	} = $props();
</script>

<ResponsiveDialogPortal {...portalProps}>
	<ResponsiveDialogOverlay {...overlayProps} />
	<DialogPrimitive.Content
		bind:ref
		data-slot="responsive-dialog-content"
		aria-label={title}
		class={cn(responsiveDialogContentVariants({ size }), className)}
		{...restProps}
	>
		<div class="mx-auto mb-5 h-1.5 w-12 rounded-full bg-muted sm:hidden"></div>
		<div class="flex items-center justify-between">
			<DialogPrimitive.Title class="text-lg font-semibold">{title}</DialogPrimitive.Title>
			<DialogPrimitive.Close
				class="relative rounded-md p-1 text-muted-foreground after:absolute after:-inset-2 after:content-[''] hover:text-foreground"
				aria-label="Close"
			>
				<X class="size-4" />
			</DialogPrimitive.Close>
		</div>
		{@render children?.()}
	</DialogPrimitive.Content>
</ResponsiveDialogPortal>
