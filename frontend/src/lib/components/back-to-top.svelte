<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import { ArrowUp } from '@lucide/svelte';
	import { onMount } from 'svelte';

	/**
	 * A floating "Back to top" for long pages (#604). The app scrolls inside #main-scroll, not
	 * the window, so it watches that element. It appears only on a page that overflows, once the
	 * reader is half a screen down, and sits inside the page area so it clears the bottom navigation on a phone.
	 */
	let { scrollerId = 'main-scroll' }: { scrollerId?: string } = $props();

	let shown = $state(false);

	const scroller = () => document.getElementById(scrollerId);

	function update() {
		const el = scroller();
		if (!el) return;
		// Only a page that runs past the bottom of the screen, and only once the reader is
		// half a screen down: at the top there is nowhere to go back to.
		const overflows = el.scrollHeight > el.clientHeight;
		shown = overflows && el.scrollTop > el.clientHeight * 0.5;
	}

	// Scroll events do not bubble, so listen in the capture phase rather than needing the
	// element to exist when this component mounts.
	onMount(() => {
		const onScroll = (e: Event) => {
			if ((e.target as HTMLElement | null)?.id === scrollerId) update();
		};
		document.addEventListener('scroll', onScroll, { capture: true, passive: true });
		update();
		return () => document.removeEventListener('scroll', onScroll, { capture: true });
	});

	// Focus follows the scroll so it is never left on a button that has just vanished (§20a).
	function backToTop() {
		const el = scroller();
		if (!el) return;
		const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
		el.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
		const target = el.querySelector<HTMLElement>('h1') ?? el;
		if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
		target.focus({ preventScroll: true });
	}
</script>

{#if shown}
	<Button
		variant="secondary"
		size="icon"
		class="absolute right-4 bottom-4 z-20 rounded-full shadow-md pointer-coarse:size-11"
		data-testid="back-to-top"
		aria-label="Back to top"
		onclick={backToTop}
	>
		<ArrowUp class="size-4" />
	</Button>
{/if}
