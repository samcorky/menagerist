<script lang="ts">
	import './layout.css';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { onNavigate } from '$app/navigation';
	import { CirclePlus, LayoutGrid, Search, Shapes } from '@lucide/svelte';
	import { Toaster } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button/index.js';
	import ThemeToggle from '$lib/components/theme-toggle.svelte';
	import { themeController } from '$lib/theme.svelte.js';
	import { captureController } from '$lib/capture.svelte.js';
	import CaptureSheet from '$lib/components/capture-sheet.svelte';

	let { children } = $props();

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
	const nodesActive = $derived(
		pathname.startsWith(resolve('/nodes')) && !pathname.startsWith(resolve('/nodes/new'))
	);
	const newActive = $derived(captureController.open);
	const typesActive = $derived(pathname.startsWith(resolve('/types')));

	$effect(() => {
		function handleKeydown(e: KeyboardEvent) {
			const tag = (e.target as HTMLElement).tagName;
			if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement).isContentEditable)
				return;
			if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
				e.preventDefault();
				captureController.show();
			}
		}
		window.addEventListener('keydown', handleKeydown);
		return () => window.removeEventListener('keydown', handleKeydown);
	});
</script>

<svelte:head>
	<link rel="icon" href="/logo.svg" />
</svelte:head>

<Toaster richColors position="top-right" />
<CaptureSheet />

<div class="flex min-h-screen flex-col">
	<header
		style="view-transition-name: site-header"
		class="sticky top-0 z-50 border-b bg-background/95 backdrop-blur"
	>
		<div class="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
			<a href={resolve('/')} class="flex items-center gap-2 text-base font-semibold tracking-tight">
				<img src="/logo.svg" alt="" aria-hidden="true" class="size-7" />
				Menagerist
			</a>

			<nav class="hidden items-center gap-1 md:flex">
				<Button variant={nodesActive ? 'secondary' : 'ghost'} size="sm" href={resolve('/nodes')}>
					<LayoutGrid class="size-4" />
					Nodes
				</Button>
				<Button variant={typesActive ? 'secondary' : 'ghost'} size="sm" href={resolve('/types')}>
					<Shapes class="size-4" />
					Types
				</Button>
				<Button size="sm" onclick={() => captureController.show()}>
					<CirclePlus class="size-4" />
					New node
				</Button>
				<ThemeToggle />
			</nav>

			<div class="flex items-center gap-1 md:hidden">
				<Button variant="ghost" size="icon" href="{resolve('/nodes')}?search=1" aria-label="Search">
					<Search class="size-4" />
				</Button>
				<ThemeToggle />
			</div>
		</div>
	</header>

	<div class="flex-1 pb-16 md:pb-0">
		{@render children()}
	</div>

	<nav
		style="view-transition-name: site-nav; padding-bottom: env(safe-area-inset-bottom)"
		class="fixed right-0 bottom-0 left-0 z-50 border-t bg-background/95 backdrop-blur md:hidden"
	>
		<div class="flex items-center justify-around px-2 py-1">
			<a
				href={resolve('/nodes')}
				class="flex flex-col items-center gap-0.5 rounded-xl px-5 py-2 transition-colors {nodesActive
					? 'text-foreground'
					: 'text-muted-foreground hover:text-foreground'}"
				aria-current={nodesActive ? 'page' : undefined}
			>
				<LayoutGrid class="size-5" />
				<span class="text-[10px] font-medium">Nodes</span>
			</a>

			<button
				onclick={() => captureController.show()}
				class="flex flex-col items-center gap-0.5 rounded-xl px-5 py-2 transition-colors {newActive
					? 'text-primary'
					: 'text-muted-foreground hover:text-foreground'}"
			>
				<CirclePlus class="size-6" />
				<span class="text-[10px] font-medium">New</span>
			</button>

			<a
				href={resolve('/types')}
				class="flex flex-col items-center gap-0.5 rounded-xl px-5 py-2 transition-colors {typesActive
					? 'text-foreground'
					: 'text-muted-foreground hover:text-foreground'}"
				aria-current={typesActive ? 'page' : undefined}
			>
				<Shapes class="size-5" />
				<span class="text-[10px] font-medium">Types</span>
			</a>
		</div>
	</nav>
</div>
