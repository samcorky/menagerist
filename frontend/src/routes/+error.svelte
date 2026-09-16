<script lang="ts">
	import type { Component } from 'svelte';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { Button } from '$lib/components/ui/button/index.js';
	import { PackageSearch, ServerCrash, TriangleAlert } from '@lucide/svelte';

	interface ErrorConfig {
		icon: Component;
		heading: string;
		description: string;
		primaryLabel: string;
		primaryAction: 'reload' | 'href';
		primaryHref?: string;
		secondaryLabel?: string;
		secondaryHref?: string;
	}

	const config = $derived.by((): ErrorConfig => {
		const status = page.status;
		if (status === 404) {
			return {
				icon: PackageSearch,
				heading: "We couldn't find this page",
				description: "The page you're looking for doesn't exist, or may have been moved.",
				primaryLabel: 'Back to collection',
				primaryAction: 'href',
				primaryHref: resolve('/collection')
			};
		}
		if (status >= 500 && status < 600) {
			return {
				icon: ServerCrash,
				heading: 'Something went wrong',
				description:
					'Something went wrong on our end. Try reloading the page, or check back in a moment.',
				primaryLabel: 'Reload',
				primaryAction: 'reload',
				secondaryLabel: 'Back to collection',
				secondaryHref: resolve('/')
			};
		}
		return {
			icon: TriangleAlert,
			heading: 'Something went wrong',
			description: 'An unexpected error occurred. Try reloading the page.',
			primaryLabel: 'Reload',
			primaryAction: 'reload',
			secondaryLabel: 'Back to collection',
			secondaryHref: resolve('/')
		};
	});

	const Icon = $derived(config.icon);
</script>

<svelte:head>
	<title>Error {page.status} — Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-3xl flex-col items-center gap-5 py-20 text-center">
		<div class="flex size-16 items-center justify-center rounded-2xl bg-muted">
			<Icon class="size-8 text-muted-foreground" />
		</div>

		<div class="space-y-1.5">
			<p class="text-sm font-medium text-muted-foreground">{page.status}</p>
			<h1 class="font-heading text-2xl font-semibold tracking-tight">{config.heading}</h1>
			<p class="max-w-xs text-muted-foreground">{config.description}</p>
		</div>

		<div class="flex flex-wrap items-center justify-center gap-3">
			{#if config.primaryAction === 'reload'}
				<Button size="lg" onclick={() => location.reload()}>
					{config.primaryLabel}
				</Button>
			{:else}
				<Button size="lg" href={config.primaryHref}>
					{config.primaryLabel}
				</Button>
			{/if}

			{#if config.secondaryLabel && config.secondaryHref}
				<Button variant="outline" size="lg" href={config.secondaryHref}>
					{config.secondaryLabel}
				</Button>
			{/if}
		</div>
	</div>
</main>
