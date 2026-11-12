<script lang="ts">
	import { NativeSelect, NativeSelectOption } from '$lib/components/ui/native-select/index.js';

	export type Section = { key: string; label: string; count: number; href: string };

	// Picks which section of a long settings page to show. A list of links beside the page on a
	// desktop, a native select on a phone; the parent chooses one so only one exists in the DOM.
	// Each section is a real link, so it can be bookmarked and the back button steps through them.
	let {
		sections,
		active,
		variant,
		onselect
	}: {
		sections: Section[];
		active: string;
		variant: 'list' | 'select';
		onselect?: (section: Section) => void;
	} = $props();
</script>

{#if variant === 'list'}
	<nav aria-label="Settings sections">
		<ul class="flex flex-col gap-0.5">
			{#each sections as section (section.key)}
				<li>
					<!-- eslint-disable svelte/no-navigation-without-resolve -- the parent passes a resolve()d href -->
					<a
						href={section.href}
						data-sveltekit-noscroll
						aria-current={section.key === active ? 'page' : undefined}
						class="flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm outline-none hover:bg-muted/50 focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-[current=page]:bg-muted aria-[current=page]:font-medium"
					>
						<span>{section.label}</span>
						<span class="text-xs text-muted-foreground">{section.count}</span>
					</a>
					<!-- eslint-enable svelte/no-navigation-without-resolve -->
				</li>
			{/each}
		</ul>
	</nav>
{:else}
	<NativeSelect
		aria-label="Settings section"
		class="w-full"
		value={active}
		onchange={(event) => {
			const section = sections.find((s) => s.key === event.currentTarget.value);
			if (section) onselect?.(section);
		}}
	>
		{#each sections as section (section.key)}
			<NativeSelectOption value={section.key}>{section.label} ({section.count})</NativeSelectOption>
		{/each}
	</NativeSelect>
{/if}
