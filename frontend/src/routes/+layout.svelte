<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import { resolve } from '$app/paths';
	import { Plus } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<header class="sticky top-0 z-50 border-b bg-background">
	<div class="mx-auto flex max-w-4xl items-center justify-between px-6 py-3">
		<a href={resolve('/')} class="text-lg font-semibold tracking-tight">Menagerist</a>
		<Button size="sm" href={resolve('/nodes/new')}>
			<Plus class="size-4" />
			New node
		</Button>
	</div>
</header>

{@render children()}
