<script lang="ts">
	import { Telescope } from '@lucide/svelte';
</script>

<svelte:head>
	<title>Explore — Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-3xl flex-col gap-6">
		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Explore</h1>
			<p class="mt-1 text-muted-foreground">See how your items connect to each other.</p>
		</div>

		<div class="flex flex-col items-center gap-5 py-16 text-center">
			<div class="flex size-16 items-center justify-center rounded-2xl bg-muted">
				<Telescope class="size-8 text-muted-foreground" />
			</div>
			<div class="space-y-1.5">
				<p class="font-heading text-xl font-semibold">Coming soon</p>
				<p class="max-w-xs text-sm text-muted-foreground">
					The connections map will let you visually explore relationships across your entire
					collection.
				</p>
			</div>
		</div>
	</div>
</main>
