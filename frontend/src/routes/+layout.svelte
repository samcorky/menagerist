<script lang="ts">
	import './layout.css';
	import { resolve } from '$app/paths';
	import { Plus } from '@lucide/svelte';
	import { Toaster } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button/index.js';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href="/logo.svg" /></svelte:head>

<Toaster richColors position="top-right" />

<div class="flex min-h-screen flex-col">
	<header class="sticky top-0 z-50 border-b bg-background">
		<div class="mx-auto flex max-w-4xl items-center justify-between px-6 py-3">
			<a href={resolve('/')} class="flex items-center gap-2 text-lg font-semibold tracking-tight">
				<img src="/logo.svg" alt="" aria-hidden="true" class="size-8" />
				Menagerist
			</a>
			<nav class="flex items-center gap-3">
				<a href={resolve('/node-types')} class="text-sm text-muted-foreground hover:text-foreground"
					>Types</a
				>
				<Button size="sm" href={resolve('/nodes/new')}>
					<Plus class="size-4" />
					New node
				</Button>
			</nav>
		</div>
	</header>

	{@render children()}
</div>
