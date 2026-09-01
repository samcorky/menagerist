<script lang="ts">
	import { resolve } from '$app/paths';
	import { Tag, ArrowLeftRight, ChevronRight } from '@lucide/svelte';
</script>

<svelte:head>
	<title>Settings — Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-2xl flex-col gap-8">
		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Settings</h1>
			<p class="mt-1 text-muted-foreground">Manage your collection structure.</p>
		</div>

		<div class="grid gap-4">
			<a href={resolve('/settings/categories')} class="group block">
				<div
					class="flex items-center justify-between rounded-xl border bg-card p-5 transition-colors group-hover:bg-muted/50"
				>
					<div class="flex items-start gap-4">
						<div
							class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:text-foreground"
						>
							<Tag class="size-5" />
						</div>
						<div>
							<p class="font-heading font-semibold">Categories</p>
							<p class="mt-0.5 text-sm text-muted-foreground">
								Organise your collection with types like "Film", "Person", or "Event".
							</p>
						</div>
					</div>
					<ChevronRight
						class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
					/>
				</div>
			</a>

			<a href={resolve('/settings/relationships')} class="group block">
				<div
					class="flex items-center justify-between rounded-xl border bg-card p-5 transition-colors group-hover:bg-muted/50"
				>
					<div class="flex items-start gap-4">
						<div
							class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:text-foreground"
						>
							<ArrowLeftRight class="size-5" />
						</div>
						<div>
							<p class="font-heading font-semibold">Relationship types</p>
							<p class="mt-0.5 text-sm text-muted-foreground">
								Define how items connect — "Directed by", "Signed by", "Part of".
							</p>
						</div>
					</div>
					<ChevronRight
						class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
					/>
				</div>
			</a>
		</div>
	</div>
</main>
