<script lang="ts">
	import './layout.css';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { onNavigate, goto } from '$app/navigation';
	import { CirclePlus, LayoutGrid, House, Settings, Library, Menu, Search } from '@lucide/svelte';
	import { onMount, setContext } from 'svelte';
	import { Toaster } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button/index.js';
	import { TooltipProvider } from '$lib/components/ui/tooltip/index.js';
	import AppSidebar from '$lib/components/app-sidebar.svelte';
	import { sidebar } from '$lib/sidebar.svelte';
	import { isTextEntry } from '$lib/text-entry';
	import { MediaQuery } from 'svelte/reactivity';
	import { PAGE_ALIGN, type PageAlignSource } from '$lib/page-context';
	import { inlineSearch } from '$lib/viewport.svelte.js';
	import IconButton from '$lib/components/icon-button.svelte';
	import ThemeToggle from '$lib/components/theme-toggle.svelte';
	import UserMenu from '$lib/components/user-menu.svelte';
	import { Spinner } from '$lib/components/ui/spinner/index.js';
	import { auth } from '$lib/auth.svelte.js';
	import { guardDecision } from '$lib/auth';
	import { animatesNavigation } from '$lib/view-transition';
	import { themeController } from '$lib/theme.svelte.js';
	import { captureController } from '$lib/capture.svelte.js';
	import { searchPaletteController } from '$lib/search-palette.svelte.js';
	import SearchPalette from '$lib/components/search-palette.svelte';
	import CaptureSheet from '$lib/components/capture-sheet.svelte';
	import { registerShortcut, attachShortcuts } from '$lib/shortcuts.svelte';
	import ShortcutsHelpDialog from '$lib/components/shortcuts-help-dialog.svelte';

	// On a phone the keyboard takes half the screen, so the bottom bar steps aside while a text
	// field has focus instead of riding above the keyboard.
	const touch = new MediaQuery('any-hover: none', false);
	let fieldFocused = $state(false);
	const keyboardUp = $derived(touch.current && fieldFocused);
	// The bar comes back a moment after focus leaves the field, not at once: it changes the page's
	// height, and doing that between pressing and lifting a finger on Save loses the tap.
	let restoreTimer: ReturnType<typeof setTimeout> | undefined;
	function trackFocus(event: FocusEvent) {
		clearTimeout(restoreTimer);
		if (event.type === 'focusin' && isTextEntry(event.target as HTMLElement | null)) {
			fieldFocused = true;
		} else {
			restoreTimer = setTimeout(() => (fieldFocused = false), 300);
		}
	}

	let { children } = $props();

	let helpOpen = $state(false);

	$effect(() => {
		themeController.init();
	});

	$effect(() => {
		function suppressViewTransitionAbort(e: PromiseRejectionEvent) {
			if (e.reason instanceof DOMException && e.reason.name === 'InvalidStateError') {
				e.preventDefault();
			}
		}
		window.addEventListener('unhandledrejection', suppressViewTransitionAbort);
		return () => window.removeEventListener('unhandledrejection', suppressViewTransitionAbort);
	});

	onNavigate((navigation) => {
		if (!document.startViewTransition || !animatesNavigation(navigation)) return;
		return new Promise((done) => {
			const transition = document.startViewTransition(async () => {
				done();
				await navigation.complete.catch(() => {});
			});
			transition.finished.catch(() => {});
		});
	});

	onMount(() => {
		void auth.init();
	});

	const pathname = $derived(page.url.pathname);
	const decision = $derived(
		guardDecision({
			pathname,
			search: page.url.search,
			hash: page.url.hash,
			setupRequired: auth.setupRequired,
			signedIn: auth.signedIn,
			passwordExpired: auth.passwordExpired,
			rememberPath: !auth.leftOnPurpose
		})
	);
	const showPage = $derived(auth.ready && decision.action === 'allow');
	// Navigation is only useful once signed in and free to use it.
	const showNav = $derived(auth.signedIn && !auth.passwordExpired);

	$effect(() => {
		if (auth.ready && decision.action === 'redirect') {
			// The guard builds same-origin paths; the app has no base path.
			// eslint-disable-next-line svelte/no-navigation-without-resolve
			void goto(decision.to, { replaceState: true });
		}
	});

	// Pages sit against the sidebar when there is one, and centre on the signed-out screens.
	const pageAlign: PageAlignSource = {
		get current() {
			return showNav ? 'start' : 'center';
		}
	};
	setContext(PAGE_ALIGN, pageAlign);

	const homeActive = $derived(pathname === resolve('/'));
	const itemsActive = $derived(pathname.startsWith(resolve('/items')));
	const collectionsActive = $derived(pathname.startsWith(resolve('/collections')));
	const newActive = $derived(captureController.open);
	const searchActive = $derived(searchPaletteController.open);
	const settingsActive = $derived(pathname.startsWith(resolve('/settings')));

	$effect(() => {
		return registerShortcut({
			id: 'global-quick-capture-mod-k',
			keys: '$mod+k',
			description: 'Quick capture',
			group: 'Add item',
			handler: (e) => {
				if (!showNav) return;
				e.preventDefault();
				captureController.show();
			}
		});
	});

	$effect(() => {
		return registerShortcut({
			id: 'global-quick-capture-n',
			keys: 'n',
			description: 'Quick capture',
			group: 'Add item',
			handler: () => showNav && captureController.show()
		});
	});

	$effect(() => {
		return registerShortcut({
			id: 'global-nav-collection',
			keys: 'g c',
			description: 'Go to Collection',
			group: 'Global',
			handler: () => goto(resolve('/items'))
		});
	});

	$effect(() => {
		return registerShortcut({
			id: 'global-nav-settings',
			keys: 'g s',
			description: 'Go to Settings',
			group: 'Global',
			handler: () => goto(resolve('/settings'))
		});
	});

	$effect(() => {
		return registerShortcut({
			id: 'global-nav-explore',
			keys: 'g e',
			description: 'Go to Explore',
			group: 'Global',
			handler: () => goto(resolve('/explore'))
		});
	});

	$effect(() => {
		return registerShortcut({
			id: 'global-help',
			keys: '[Shift]+?',
			description: 'Show keyboard shortcuts',
			group: 'Global',
			handler: () => (helpOpen = true)
		});
	});

	$effect(() => {
		return registerShortcut({
			id: 'global-search',
			keys: '[Shift]+/',
			description: 'Search',
			group: 'Search',
			handler: (e) => {
				if (!showNav) return;
				e.preventDefault();
				searchPaletteController.show();
			}
		});
	});

	$effect(() => attachShortcuts(window));
</script>

<svelte:window
	onresize={() => sidebar.setWidth(window.innerWidth)}
	onfocusin={trackFocus}
	onfocusout={trackFocus}
/>

<svelte:head>
	<link rel="icon" href="/favicon.svg" type="image/svg+xml" />
</svelte:head>

<Toaster richColors position="top-right" offset={{ top: '76px' }} mobileOffset={{ top: '68px' }} />
<CaptureSheet />
{#if !inlineSearch.current}
	<SearchPalette />
{/if}
<ShortcutsHelpDialog open={helpOpen} onOpenChange={(v) => (helpOpen = v)} />

<TooltipProvider>
	<div class="flex h-dvh flex-col">
		<header
			style="view-transition-name: site-header"
			class="sticky top-0 z-30 border-b bg-background/95 backdrop-blur"
		>
			<div class="flex items-center gap-2 px-3 py-1.5">
				{#if showNav}
					<IconButton
						label="Menu"
						labelOnTouch={false}
						aria-controls="app-sidebar"
						aria-expanded={sidebar.mode === 'drawer'
							? sidebar.drawerOpen
							: sidebar.mode === 'expanded'}
						onclick={() => sidebar.toggle()}
					>
						<Menu />
					</IconButton>
				{/if}
				<a
					href={resolve('/')}
					class="flex items-center gap-2 text-base font-semibold tracking-tight"
				>
					<span
						aria-hidden="true"
						class="size-6 shrink-0 bg-foreground"
						style="mask-image: url(/logo.svg); mask-size: contain; mask-repeat: no-repeat; mask-position: center; -webkit-mask-image: url(/logo.svg); -webkit-mask-size: contain; -webkit-mask-repeat: no-repeat; -webkit-mask-position: center;"
					></span>
					Menagerist
				</a>

				{#if showNav && inlineSearch.current}
					<div class="flex-1 px-2">
						<div class="mx-auto w-full max-w-xl">
							<SearchPalette inline />
						</div>
					</div>
				{:else}
					<div class="flex-1"></div>
				{/if}

				{#if showNav}
					{#if !inlineSearch.current}
						<IconButton
							label="Search"
							shortcut="/"
							labelOnTouch={false}
							class="max-md:hidden"
							onclick={() => searchPaletteController.show()}
						>
							<Search />
						</IconButton>
					{/if}
					<IconButton
						label="New item"
						shortcut="N"
						variant="default"
						class="max-md:hidden"
						onclick={() => goto(resolve('/items/new'))}
					>
						<CirclePlus />
					</IconButton>
				{/if}
				<ThemeToggle />
				<UserMenu />
			</div>
		</header>

		<div class="flex min-h-0 flex-1">
			{#if showNav}
				<AppSidebar />
			{/if}
			<div id="main-scroll" class="min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
				{#if showPage}
					{@render children()}
				{:else if auth.loadFailed}
					<main class="flex flex-1 flex-col items-center gap-3 px-4 py-16 text-center">
						<h1 class="font-heading text-xl font-semibold">Can't reach Menagerist</h1>
						<p class="text-muted-foreground">Check your connection, then try again.</p>
						<Button class="pointer-coarse:h-11" onclick={() => auth.init()}>Try again</Button>
					</main>
				{:else}
					<div class="flex justify-center py-16">
						<Spinner class="size-6" />
					</div>
				{/if}
			</div>
		</div>

		{#if showNav}
			<nav
				style="view-transition-name: site-nav; padding-bottom: env(safe-area-inset-bottom)"
				class="shrink-0 border-t bg-background/95 backdrop-blur md:hidden {keyboardUp
					? 'h-0 overflow-hidden border-t-0 p-0 opacity-0'
					: ''}"
			>
				<div class="flex items-center px-0 py-1">
					<a
						href={resolve('/')}
						class="flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-0 py-1.5 transition-colors {homeActive
							? 'text-foreground'
							: 'text-muted-foreground hover:text-foreground'}"
						aria-current={homeActive ? 'page' : undefined}
					>
						<House class="size-5" />
						<span class="max-w-full truncate text-[10px] font-medium tracking-tighter">Home</span>
					</a>

					<a
						href={resolve('/items')}
						class="flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-0 py-1.5 transition-colors {itemsActive
							? 'text-foreground'
							: 'text-muted-foreground hover:text-foreground'}"
						aria-current={itemsActive ? 'page' : undefined}
					>
						<LayoutGrid class="size-5" />
						<span class="max-w-full truncate text-[10px] font-medium tracking-tighter">Items</span>
					</a>

					<a
						href={resolve('/collections')}
						class="flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-0 py-1.5 transition-colors {collectionsActive
							? 'text-foreground'
							: 'text-muted-foreground hover:text-foreground'}"
						aria-current={collectionsActive ? 'page' : undefined}
					>
						<Library class="size-5" />
						<span class="max-w-full truncate text-[10px] font-medium tracking-tighter"
							>Collections</span
						>
					</a>

					<button
						onclick={() => searchPaletteController.show()}
						aria-haspopup="dialog"
						aria-label="Search"
						class="flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-0 py-1.5 transition-colors {searchActive
							? 'text-foreground'
							: 'text-muted-foreground hover:text-foreground'}"
					>
						<Search class="size-5" />
						<span class="max-w-full truncate text-[10px] font-medium tracking-tighter">Search</span>
					</button>

					<button
						onclick={() => captureController.show()}
						class="flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-0 py-1.5 transition-colors {newActive
							? 'text-primary'
							: 'text-muted-foreground hover:text-foreground'}"
					>
						<CirclePlus class="size-6" />
						<span class="max-w-full truncate text-[10px] font-medium tracking-tighter">New</span>
					</button>

					<a
						href={resolve('/settings')}
						class="flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-0 py-1.5 transition-colors {settingsActive
							? 'text-foreground'
							: 'text-muted-foreground hover:text-foreground'}"
						aria-current={settingsActive ? 'page' : undefined}
					>
						<Settings class="size-5" />
						<span class="max-w-full truncate text-[10px] font-medium tracking-tighter"
							>Settings</span
						>
					</a>
				</div>
			</nav>
		{/if}
	</div>
</TooltipProvider>
