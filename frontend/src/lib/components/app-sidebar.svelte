<script lang="ts">
	import { tick } from 'svelte';
	import { fade, fly, type TransitionConfig } from 'svelte/transition';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { BookOpen, Settings } from '@lucide/svelte';
	import { auth } from '$lib/auth.svelte.js';
	import {
		activeManageHref,
		mainDestinations,
		manageGroups,
		type ManageItem
	} from '$lib/manage-nav';
	import { sidebar } from '$lib/sidebar.svelte';
	import CollapsibleSection from '$lib/components/collapsible-section.svelte';
	import PageScrollLock from '$lib/components/page-scroll-lock.svelte';
	import * as Tooltip from '$lib/components/ui/tooltip/index.js';
	import { cn } from '$lib/utils.js';

	const can = (permission: Parameters<typeof auth.can>[0]) => auth.can(permission);
	const pathname = $derived(page.url.pathname);
	const groups = $derived(manageGroups(can));
	const active = $derived(activeManageHref(pathname, can));
	const rail = $derived(sidebar.mode === 'rail');
	const hubActive = $derived(pathname === '/settings' || pathname === '/admin');

	let panel = $state<HTMLElement | null>(null);
	// Where focus was when the drawer opened, so closing it hands focus back (the burger).
	let opener: HTMLElement | null = null;

	// One highlight that slides to the current destination, instead of each link switching its own
	// background. It is placed without animation the first time, so it never slides in from the corner.
	let indicator = $state<HTMLElement | null>(null);
	let placed = $state(false);
	function place() {
		if (!panel || !indicator) return;
		const link = panel.querySelector<HTMLElement>('a[aria-current="page"]');
		if (!link) {
			indicator.style.opacity = '0';
			return;
		}
		const box = link.getBoundingClientRect();
		const within = panel.getBoundingClientRect();
		const x = box.left - within.left + panel.scrollLeft;
		const y = box.top - within.top + panel.scrollTop;
		indicator.style.opacity = '1';
		indicator.style.width = `${box.width}px`;
		indicator.style.height = `${box.height}px`;
		indicator.style.transform = `translate(${x}px, ${y}px)`;
		if (!placed) requestAnimationFrame(() => (placed = true));
	}

	// Follow the current page, the sidebar's width and anything that moves the links.
	$effect(() => {
		void [active, sidebar.mode, sidebar.drawerOpen, panel, indicator];
		void tick().then(place);
	});
	// Changing between rail and full sidebar moves the links for a moment (headings fold, margins
	// ease), so the highlight is pinned to the current link each frame instead of gliding behind it.
	$effect(() => {
		void rail;
		if (!indicator) return;
		const node = indicator;
		const end = performance.now() + 300;
		let frame = 0;
		node.style.transition = 'none';
		const follow = () => {
			place();
			if (performance.now() < end) frame = requestAnimationFrame(follow);
			else node.style.transition = '';
		};
		frame = requestAnimationFrame(follow);
		return () => {
			cancelAnimationFrame(frame);
			node.style.transition = '';
		};
	});
	$effect(() => {
		if (!panel) return;
		const node = panel;
		const observer = new ResizeObserver(place);
		observer.observe(node);
		node.addEventListener('animationend', place);
		node.addEventListener('transitionend', place);
		return () => {
			observer.disconnect();
			node.removeEventListener('animationend', place);
			node.removeEventListener('transitionend', place);
		};
	});

	// Panels slide (200-250 ms); with reduced motion they only fade, briefly (design §22).
	const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
	function slideIn(node: Element): TransitionConfig {
		return reduced() ? fade(node, { duration: 100 }) : fly(node, { x: -256, duration: 220 });
	}
	function scrim(node: Element): TransitionConfig {
		return fade(node, { duration: reduced() ? 100 : 180 });
	}

	// Tab and Shift+Tab wrap inside the open drawer instead of reaching the page behind it.
	function trapFocus(event: KeyboardEvent) {
		if (event.key !== 'Tab' || !panel) return;
		const focusable = [...panel.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')];
		if (focusable.length === 0) return;
		const first = focusable[0];
		const last = focusable[focusable.length - 1];
		const active = document.activeElement;
		if (event.shiftKey && (active === first || !panel.contains(active))) {
			event.preventDefault();
			last.focus();
		} else if (!event.shiftKey && (active === last || !panel.contains(active))) {
			event.preventDefault();
			first.focus();
		}
	}

	// Choosing a destination in the drawer closes it.
	$effect(() => {
		void pathname;
		sidebar.closeDrawer();
	});

	// Opening the drawer moves focus into it; closing it gives focus back.
	$effect(() => {
		if (sidebar.mode === 'drawer' && sidebar.drawerOpen) {
			const active = document.activeElement;
			opener = active instanceof HTMLElement && active !== document.body ? active : null;
			void tick().then(() => panel?.querySelector<HTMLElement>('a, button')?.focus());
		} else if (opener) {
			opener.focus();
			opener = null;
		}
	});

	const linkClass = (current: boolean) =>
		cn(
			'flex h-8 items-center gap-2 rounded-xl px-2 text-sm text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/30 pointer-coarse:h-11',
			current && 'font-medium text-foreground'
		);
</script>

<svelte:window
	onkeydown={(e) => {
		if (e.key === 'Escape' && sidebar.mode === 'drawer' && sidebar.drawerOpen) {
			sidebar.closeDrawer();
		}
	}}
/>

{#snippet row(item: ManageItem, current: boolean, props: Record<string, unknown> = {})}
	{@const Icon = item.icon}
	<!-- The icon sits in the same place in every mode, so changing mode never moves it; the label
	     stays in the page (and for screen readers) and only fades while the rail clips it. -->
	<a
		{...props}
		href={resolve(item.href as '/')}
		aria-current={current ? 'page' : undefined}
		class={linkClass(current)}
	>
		<Icon class="size-4 shrink-0" />
		<span
			class={cn(
				'truncate whitespace-nowrap transition-opacity duration-150 motion-reduce:transition-none',
				rail && 'opacity-0'
			)}>{item.label}</span
		>
	</a>
{/snippet}

{#snippet entry(item: ManageItem, current: boolean)}
	<!-- Always inside a tooltip (off outside the rail), so the row is the same element in both modes
	     and its label can fade rather than appear. -->
	<Tooltip.Root disabled={!rail}>
		<Tooltip.Trigger>
			{#snippet child({ props })}
				{@render row(item, current, props)}
			{/snippet}
		</Tooltip.Trigger>
		<Tooltip.Content side="right">{item.label}</Tooltip.Content>
	</Tooltip.Root>
{/snippet}

{#snippet docs(props: Record<string, unknown> = {})}
	<a {...props} href={resolve('/api/docs' as '/')} target="_blank" class={linkClass(false)}>
		<BookOpen class="size-4 shrink-0" />
		<span
			class={cn(
				'truncate whitespace-nowrap transition-opacity duration-150 motion-reduce:transition-none',
				rail && 'opacity-0'
			)}>API docs</span
		>
	</a>
{/snippet}

{#snippet body()}
	<span
		bind:this={indicator}
		aria-hidden="true"
		class={cn(
			'pointer-events-none absolute top-0 left-0 -z-10 rounded-xl bg-secondary opacity-0',
			placed && 'transition-[transform,opacity] duration-200 ease-out motion-reduce:transition-none'
		)}
	></span>
	<ul class="flex flex-col gap-0.5">
		{#each mainDestinations as item (item.href)}
			<li>{@render entry(item, active === item.href)}</li>
		{/each}
	</ul>

	{#each groups as group (group.label)}
		{#if group.items.length > 0}
			<!-- The same section in both modes: the rail folds the heading away and shows a divider. -->
			<CollapsibleSection
				id={`nav-${group.label.toLowerCase()}`}
				title={group.label}
				heading="p"
				titleClass="text-xs font-medium text-muted-foreground"
				forceOpen={group.items.some((item) => item.href === active)}
				bare={rail}
				class={cn(
					'border-t transition-[margin,padding,gap,border-color] duration-200 motion-reduce:transition-none',
					rail ? 'mt-2 gap-0 border-border pt-2' : 'mt-3 gap-1 border-transparent'
				)}
			>
				<ul class="flex flex-col gap-0.5">
					{#each group.items as item (item.href)}
						<li>{@render entry(item, active === item.href)}</li>
					{/each}
				</ul>
			</CollapsibleSection>
		{/if}
	{/each}

	<div class="mt-auto flex flex-col gap-0.5 pt-3">
		{@render entry({ href: '/settings', label: 'Settings', icon: Settings }, hubActive)}
		<Tooltip.Root disabled={!rail}>
			<Tooltip.Trigger>
				{#snippet child({ props })}
					{@render docs(props)}
				{/snippet}
			</Tooltip.Trigger>
			<Tooltip.Content side="right">API docs</Tooltip.Content>
		</Tooltip.Root>
	</div>
{/snippet}

{#if sidebar.mode === 'drawer'}
	{#if sidebar.drawerOpen}
		<div
			role="dialog"
			aria-modal="true"
			aria-label="Menu"
			tabindex="-1"
			class="fixed inset-0 z-[55]"
			onkeydown={trapFocus}
		>
			<PageScrollLock />
			<button
				type="button"
				tabindex="-1"
				aria-label="Close menu"
				class="absolute inset-0 bg-black/40"
				transition:scrim
				onclick={() => sidebar.closeDrawer()}
			></button>
			<nav
				bind:this={panel}
				id="app-sidebar"
				aria-label="Main"
				class="absolute inset-y-0 left-0 isolate z-10 flex w-64 flex-col overflow-x-hidden overflow-y-auto border-r bg-background p-2 shadow-xl"
				style="padding-top: env(safe-area-inset-top); padding-bottom: max(0.5rem, calc(env(safe-area-inset-bottom) * 0.5)); padding-left: max(0.5rem, env(safe-area-inset-left))"
				transition:slideIn
			>
				{@render body()}
			</nav>
		</div>
	{/if}
{:else}
	<nav
		bind:this={panel}
		id="app-sidebar"
		aria-label="Main"
		class={cn(
			'relative isolate flex shrink-0 flex-col overflow-x-hidden overflow-y-auto border-r bg-background p-2 transition-[width] duration-200 ease-out motion-reduce:transition-none',
			rail ? 'w-12' : 'w-56'
		)}
		style="view-transition-name: app-sidebar"
	>
		{@render body()}
	</nav>
{/if}
