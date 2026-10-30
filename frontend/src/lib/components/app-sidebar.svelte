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
			rail && 'justify-center px-0',
			current && 'bg-secondary font-medium text-foreground'
		);
</script>

<svelte:window
	onkeydown={(e) => {
		if (e.key === 'Escape' && sidebar.mode === 'drawer' && sidebar.drawerOpen) {
			sidebar.closeDrawer();
		}
	}}
/>

{#snippet entry(item: ManageItem, current: boolean)}
	{@const Icon = item.icon}
	{#if rail}
		<Tooltip.Root>
			<Tooltip.Trigger>
				{#snippet child({ props })}
					<a
						{...props}
						href={resolve(item.href as '/')}
						aria-current={current ? 'page' : undefined}
						class={linkClass(current)}
					>
						<Icon class="size-4 shrink-0" />
						<span class="sr-only">{item.label}</span>
					</a>
				{/snippet}
			</Tooltip.Trigger>
			<Tooltip.Content side="right">{item.label}</Tooltip.Content>
		</Tooltip.Root>
	{:else}
		<a
			href={resolve(item.href as '/')}
			aria-current={current ? 'page' : undefined}
			class={linkClass(current)}
		>
			<Icon class="size-4 shrink-0" />
			<span class="animate-in truncate fade-in-0 motion-reduce:animate-none">{item.label}</span>
		</a>
	{/if}
{/snippet}

{#snippet body()}
	<ul class="flex flex-col gap-0.5">
		{#each mainDestinations as item (item.href)}
			<li>{@render entry(item, active === item.href)}</li>
		{/each}
	</ul>

	{#each groups as group (group.label)}
		{#if group.items.length > 0}
			{#if rail}
				<hr class="my-2 border-border" />
				<ul class="flex flex-col gap-0.5">
					{#each group.items as item (item.href)}
						<li>{@render entry(item, active === item.href)}</li>
					{/each}
				</ul>
			{:else}
				<CollapsibleSection
					id={`nav-${group.label.toLowerCase()}`}
					title={group.label}
					heading="p"
					titleClass="text-xs font-medium text-muted-foreground"
					forceOpen={group.items.some((item) => item.href === active)}
					class="mt-3 gap-1"
				>
					<ul class="flex flex-col gap-0.5">
						{#each group.items as item (item.href)}
							<li>{@render entry(item, active === item.href)}</li>
						{/each}
					</ul>
				</CollapsibleSection>
			{/if}
		{/if}
	{/each}

	<div class="mt-auto flex flex-col gap-0.5 pt-3">
		{@render entry({ href: '/settings', label: 'Settings', icon: Settings }, hubActive)}
		{#if rail}
			<Tooltip.Root>
				<Tooltip.Trigger>
					{#snippet child({ props })}
						<a
							{...props}
							href={resolve('/api/docs' as '/')}
							target="_blank"
							class={linkClass(false)}
						>
							<BookOpen class="size-4 shrink-0" />
							<span class="sr-only">API docs</span>
						</a>
					{/snippet}
				</Tooltip.Trigger>
				<Tooltip.Content side="right">API docs</Tooltip.Content>
			</Tooltip.Root>
		{:else}
			<a href={resolve('/api/docs' as '/')} target="_blank" class={linkClass(false)}>
				<BookOpen class="size-4 shrink-0" />
				<span class="truncate">API docs</span>
			</a>
		{/if}
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
				class="absolute inset-y-0 left-0 z-10 flex w-64 flex-col overflow-y-auto border-r bg-background p-2 shadow-xl"
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
			'flex shrink-0 flex-col overflow-y-auto border-r bg-background p-2 transition-[width] duration-200 ease-out motion-reduce:transition-none',
			rail ? 'w-12' : 'w-56'
		)}
	>
		{@render body()}
	</nav>
{/if}
