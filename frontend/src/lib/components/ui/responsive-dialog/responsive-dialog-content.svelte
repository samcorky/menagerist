<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	/**
	 * A bottom sheet on mobile (drag handle, slides up from the bottom edge) that becomes a
	 * centered dialog at the `sm` breakpoint - the app's one modal shape, per DESIGN_GUIDELINES §23.
	 */
	export const responsiveDialogContentVariants = tv({
		base: 'fixed right-0 bottom-0 left-0 z-50 max-h-[90dvh] overflow-x-hidden overflow-y-auto overscroll-contain rounded-t-2xl border-t bg-background p-6 shadow-xl sm:inset-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-full sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl sm:border',
		variants: {
			size: {
				sm: 'sm:max-w-sm',
				md: 'sm:max-w-md',
				lg: 'sm:max-w-lg',
				xl: 'sm:max-w-3xl'
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
	import PageScrollLock from '$lib/components/page-scroll-lock.svelte';
	import ResponsiveDialogPortal from './responsive-dialog-portal.svelte';
	import ResponsiveDialogOverlay from './responsive-dialog-overlay.svelte';
	import { shouldCloseSheet } from '$lib/sheet-drag';

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

	const SLIDE_OUT_MS = 180;
	let closeButton = $state<HTMLElement | null>(null);
	let drag: { id: number; startY: number; lastY: number; lastT: number; velocity: number } | null =
		null;

	function dragStart(e: PointerEvent) {
		if (!e.isPrimary || (e.pointerType === 'mouse' && e.button !== 0)) return;
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		if (ref) ref.style.transition = 'none';
		drag = {
			id: e.pointerId,
			startY: e.clientY,
			lastY: e.clientY,
			lastT: e.timeStamp,
			velocity: 0
		};
	}

	function dragMove(e: PointerEvent) {
		if (!drag || e.pointerId !== drag.id || !ref) return;
		const dt = e.timeStamp - drag.lastT;
		if (dt > 0) drag.velocity = (e.clientY - drag.lastY) / dt;
		drag.lastY = e.clientY;
		drag.lastT = e.timeStamp;
		ref.style.transform = `translateY(${Math.max(0, e.clientY - drag.startY)}px)`;
	}

	function springBack() {
		if (!ref) return;
		// Reduced motion shortens this to an instant snap via the global rule in layout.css.
		ref.style.transition = 'transform 200ms ease-out';
		ref.style.transform = '';
	}

	function dragEnd(e: PointerEvent) {
		if (!drag || e.pointerId !== drag.id || !ref) return;
		const distance = e.clientY - drag.startY;
		const close =
			e.type === 'pointerup' && shouldCloseSheet(distance, ref.offsetHeight, drag.velocity);
		drag = null;
		if (!close) return springBack();
		// Slide out first, then close through the button so a form's "Discard changes?" check
		// still runs; if the dialog stays open, the sheet returns to where it was.
		const sheet = ref;
		const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
		sheet.style.transition = reduced ? 'none' : `transform ${SLIDE_OUT_MS}ms ease-in`;
		sheet.style.transform = `translateY(${sheet.offsetHeight}px)`;
		setTimeout(
			() => {
				closeButton?.click();
				// Wait for the dialog to settle: resetting at once would flash a closing sheet
				// back into place. Only a sheet that is still open (the discard prompt) returns.
				setTimeout(() => {
					if (sheet.isConnected && sheet.dataset.state === 'open') springBack();
				}, 50);
			},
			reduced ? 0 : SLIDE_OUT_MS
		);
	}
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
		<PageScrollLock />
		<!-- Decorative: the Close button below is the accessible way to dismiss. -->
		<div
			aria-hidden="true"
			data-slot="sheet-grab-bar"
			class="-mx-6 -mt-6 flex touch-none justify-center px-6 pt-6 pb-5 sm:hidden"
			onpointerdown={dragStart}
			onpointermove={dragMove}
			onpointerup={dragEnd}
			onpointercancel={dragEnd}
		>
			<div class="h-1.5 w-12 rounded-full bg-muted"></div>
		</div>
		<div class="flex items-center justify-between">
			<DialogPrimitive.Title class="text-lg font-semibold">{title}</DialogPrimitive.Title>
			<DialogPrimitive.Close
				bind:ref={closeButton}
				class="relative rounded-md p-1 text-muted-foreground after:absolute after:-inset-2 after:content-[''] hover:text-foreground"
				aria-label="Close"
			>
				<X class="size-4" />
			</DialogPrimitive.Close>
		</div>
		{@render children?.()}
	</DialogPrimitive.Content>
</ResponsiveDialogPortal>
