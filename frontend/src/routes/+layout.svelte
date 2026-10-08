<script lang="ts">
	import './layout.css';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { onNavigate, goto } from '$app/navigation';
	import {
		CirclePlus,
		LayoutGrid,
		House,
		Settings,
		Telescope,
		BookOpen,
		Library
	} from '@lucide/svelte';
	import { Toaster } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button/index.js';
	import { TooltipProvider } from '$lib/components/ui/tooltip/index.js';
	import ThemeToggle from '$lib/components/theme-toggle.svelte';
	import { themeController } from '$lib/theme.svelte.js';
	import { captureController } from '$lib/capture.svelte.js';
	import CaptureSheet from '$lib/components/capture-sheet.svelte';
	import { registerShortcut, attachShortcuts } from '$lib/shortcuts.svelte';
	import ShortcutsHelpDialog from '$lib/components/shortcuts-help-dialog.svelte';

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
		if (!document.startViewTransition) return;
		return new Promise((done) => {
			const transition = document.startViewTransition(async () => {
				done();
				await navigation.complete.catch(() => {});
			});
			transition.finished.catch(() => {});
		});
	});

	const pathname = $derived(page.url.pathname);
	const homeActive = $derived(pathname === resolve('/'));
	const itemsActive = $derived(pathname.startsWith(resolve('/items')));
	const collectionsActive = $derived(pathname.startsWith(resolve('/collections')));
	const exploreActive = $derived(pathname.startsWith(resolve('/explore')));
	const newActive = $derived(captureController.open);
	const settingsActive = $derived(pathname.startsWith(resolve('/settings')));

	$effect(() => {
		return registerShortcut({
			id: 'global-quick-capture-mod-k',
			keys: '$mod+k',
			description: 'Quick capture',
			group: 'Add item',
			handler: (e) => {
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
			handler: () => captureController.show()
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
		if (pathname === resolve('/items')) return;
		return registerShortcut({
			id: 'global-focus-search',
			keys: '[Shift]+/',
			description: 'Focus search',
			group: 'Search',
			handler: (e) => {
				e.preventDefault();
				void goto(resolve('/items?search=1'));
			}
		});
	});

	$effect(() => attachShortcuts(window));
</script>

<svelte:head>
	<link rel="icon" href="/favicon.svg" type="image/svg+xml" />
</svelte:head>

<Toaster richColors position="top-right" offset={{ top: '76px' }} mobileOffset={{ top: '68px' }} />
<CaptureSheet />
<ShortcutsHelpDialog open={helpOpen} onOpenChange={(v) => (helpOpen = v)} />

<TooltipProvider>
	<div class="flex h-dvh flex-col">
		<header
			style="view-transition-name: site-header"
			class="sticky top-0 z-50 border-b bg-background/95 backdrop-blur"
		>
			<div class="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
				<a
					href={resolve('/')}
					class="flex items-center gap-2 text-base font-semibold tracking-tight"
				>
					<span
						aria-hidden="true"
						class="size-7 shrink-0 bg-foreground"
						style="mask-image: url(/logo.svg); mask-size: contain; mask-repeat: no-repeat; mask-position: center; -webkit-mask-image: url(/logo.svg); -webkit-mask-size: contain; -webkit-mask-repeat: no-repeat; -webkit-mask-position: center;"
					></span>
					Menagerist
				</a>

				<nav class="hidden items-center gap-1 md:flex">
					<Button variant={homeActive ? 'secondary' : 'ghost'} size="sm" href={resolve('/')}>
						<House class="size-4" />
						Home
					</Button>
					<Button variant={itemsActive ? 'secondary' : 'ghost'} size="sm" href={resolve('/items')}>
						<LayoutGrid class="size-4" />
						Items
					</Button>
					<Button
						variant={collectionsActive ? 'secondary' : 'ghost'}
						size="sm"
						href={resolve('/collections')}
					>
						<Library class="size-4" />
						Collections
					</Button>
					<Button
						variant={exploreActive ? 'secondary' : 'ghost'}
						size="sm"
						href={resolve('/explore')}
					>
						<Telescope class="size-4" />
						Explore
					</Button>
					<Button size="sm" onclick={() => goto(resolve('/items/new'))}>
						<CirclePlus class="size-4" />
						New item
					</Button>
					<Button
						variant="ghost"
						size="icon"
						href="/api/docs"
						target="_blank"
						aria-label="API docs"
					>
						<BookOpen class="size-4" />
					</Button>
					<Button
						variant={settingsActive ? 'secondary' : 'ghost'}
						size="icon"
						href={resolve('/settings')}
						aria-label="Settings"
					>
						<Settings class="size-4" />
					</Button>
					<ThemeToggle />
				</nav>

				<div class="flex items-center gap-1 md:hidden">
					<ThemeToggle />
				</div>
			</div>
		</header>

		<div id="main-scroll" class="flex-1 overflow-y-auto">
			{@render children()}
		</div>

		<nav
			style="view-transition-name: site-nav; padding-bottom: env(safe-area-inset-bottom)"
			class="shrink-0 border-t bg-background/95 backdrop-blur md:hidden"
		>
			<div class="flex items-center justify-around px-2 py-1">
				<a
					href={resolve('/')}
					class="flex flex-col items-center gap-0.5 rounded-xl px-4 py-2 transition-colors {homeActive
						? 'text-foreground'
						: 'text-muted-foreground hover:text-foreground'}"
					aria-current={homeActive ? 'page' : undefined}
				>
					<House class="size-5" />
					<span class="text-[10px] font-medium">Home</span>
				</a>

				<a
					href={resolve('/items')}
					class="flex flex-col items-center gap-0.5 rounded-xl px-3 py-2 transition-colors {itemsActive
						? 'text-foreground'
						: 'text-muted-foreground hover:text-foreground'}"
					aria-current={itemsActive ? 'page' : undefined}
				>
					<LayoutGrid class="size-5" />
					<span class="text-[10px] font-medium">Items</span>
				</a>

				<a
					href={resolve('/collections')}
					class="flex flex-col items-center gap-0.5 rounded-xl px-2 py-2 transition-colors {collectionsActive
						? 'text-foreground'
						: 'text-muted-foreground hover:text-foreground'}"
					aria-current={collectionsActive ? 'page' : undefined}
				>
					<Library class="size-5" />
					<span class="text-[10px] font-medium">Collections</span>
				</a>

				<a
					href={resolve('/explore')}
					class="flex flex-col items-center gap-0.5 rounded-xl px-3 py-2 transition-colors {exploreActive
						? 'text-foreground'
						: 'text-muted-foreground hover:text-foreground'}"
					aria-current={exploreActive ? 'page' : undefined}
				>
					<Telescope class="size-5" />
					<span class="text-[10px] font-medium">Explore</span>
				</a>

				<button
					onclick={() => captureController.show()}
					class="flex flex-col items-center gap-0.5 rounded-xl px-4 py-2 transition-colors {newActive
						? 'text-primary'
						: 'text-muted-foreground hover:text-foreground'}"
				>
					<CirclePlus class="size-6" />
					<span class="text-[10px] font-medium">New</span>
				</button>

				<a
					href={resolve('/settings')}
					class="flex flex-col items-center gap-0.5 rounded-xl px-4 py-2 transition-colors {settingsActive
						? 'text-foreground'
						: 'text-muted-foreground hover:text-foreground'}"
					aria-current={settingsActive ? 'page' : undefined}
				>
					<Settings class="size-5" />
					<span class="text-[10px] font-medium">Settings</span>
				</a>
			</div>
		</nav>
	</div>
</TooltipProvider>
