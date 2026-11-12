<script lang="ts">
	import type { Component } from 'svelte';
	import { ChevronRight } from '@lucide/svelte';

	// The one link tile used for every entry on /settings and /admin, so a new entry cannot drift
	// from the others in size, spacing, wrapping or hover and focus states.
	let {
		href,
		icon: Icon,
		title,
		description
	}: {
		href: string;
		icon: Component<{ class?: string }>;
		title: string;
		description: string;
	} = $props();
</script>

<!-- eslint-disable svelte/no-navigation-without-resolve -- callers pass a resolve()d path -->
<a
	{href}
	data-slot="settings-tile"
	class="group flex min-h-20 items-center justify-between gap-4 rounded-xl border bg-card p-5 transition-colors outline-none hover:bg-muted/50 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
>
	<div class="flex min-w-0 items-start gap-4">
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:text-foreground"
		>
			<Icon class="size-5" />
		</div>
		<div class="min-w-0">
			<p class="font-heading font-semibold [overflow-wrap:anywhere]">{title}</p>
			<p class="mt-0.5 text-sm [overflow-wrap:anywhere] text-muted-foreground">{description}</p>
		</div>
	</div>
	<ChevronRight
		class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
	/>
</a>
<!-- eslint-enable svelte/no-navigation-without-resolve -->
