<script lang="ts">
	import { tick } from 'svelte';
	import { Dices } from '@lucide/svelte';
	import { TYPE_ICONS } from '$lib/type-icons';
	import {
		TYPE_COLOUR_KEYS,
		colourClasses,
		isKnownIcon,
		randomColour,
		randomIcon,
		searchIcons
	} from '$lib/type-appearance';
	import TypeIcon from '$lib/components/type-icon.svelte';
	import { nextCardIndex, type NavKey } from '$lib/components/card-grid-nav';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { cn } from '$lib/utils.js';

	// Where an item type's icon and colour are chosen. The dice picks both at random, never
	// repeating the current choice, so a few presses is a quick way to find something that suits.
	let {
		icon = $bindable(null as string | null),
		colour = $bindable(null as string | null)
	}: { icon?: string | null; colour?: string | null } = $props();

	let open = $state(false);
	let query = $state('');
	// The icon under the pointer or the keyboard, named in the line below the grid.
	let hovered = $state<string | null>(null);
	let searchEl = $state<HTMLInputElement | null>(null);
	let gridEl = $state<HTMLElement | null>(null);
	const results = $derived(searchIcons(query));

	const gridButtons = () => [...(gridEl?.querySelectorAll<HTMLButtonElement>('button') ?? [])];

	// Arrow keys move through the grid by where the icons are, so rows and columns both work;
	// ArrowUp from the first row goes back to the search box.
	function onGridKeydown(event: KeyboardEvent, index: number) {
		if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) return;
		event.preventDefault();
		const buttons = gridButtons();
		const rects = buttons.map((b) => {
			const { top, left } = b.getBoundingClientRect();
			return { top, left };
		});
		const next = nextCardIndex(event.key as NavKey, index, rects, 'grid');
		if (next !== null) buttons[next]?.focus();
		else if (event.key === 'ArrowUp') searchEl?.focus();
	}

	function onSearchKeydown(event: KeyboardEvent) {
		if (event.key !== 'ArrowDown') return;
		const first = gridButtons()[0];
		if (!first) return;
		event.preventDefault();
		first.focus();
	}

	function setOpen(value: boolean) {
		open = value;
		if (!value) {
			query = '';
			hovered = null;
		} else {
			void tick().then(() => searchEl?.focus());
		}
	}

	// Escape closes just this panel, not the editor around it.
	function onPanelKeydown(event: KeyboardEvent) {
		if (event.key !== 'Escape' || !open) return;
		event.stopPropagation();
		setOpen(false);
	}

	function randomise() {
		icon = randomIcon(Math.random, icon);
		colour = randomColour(Math.random, colour);
	}

	const label = (key: string) => key.charAt(0).toUpperCase() + key.slice(1);
</script>

<div class="space-y-2" role="group" aria-label="Icon and colour">
	<Label>Icon and colour</Label>
	<div class="flex flex-wrap items-center gap-3">
		<div data-testid="type-appearance-preview">
			<TypeIcon {icon} {colour} boxed class="size-10 rounded-xl text-2xl" />
		</div>

		<Button
			type="button"
			variant="outline"
			size="sm"
			aria-expanded={open}
			onclick={() => setOpen(!open)}
		>
			Choose icon
		</Button>

		<Button
			type="button"
			variant="outline"
			size="icon"
			aria-label="Randomise icon and colour"
			title="Randomise icon and colour"
			onclick={randomise}
		>
			<Dices class="size-4" />
		</Button>

		{#if icon || colour}
			<Button
				type="button"
				variant="ghost"
				size="sm"
				aria-label="Clear icon and colour"
				onclick={() => {
					icon = null;
					colour = null;
				}}
			>
				Clear
			</Button>
		{/if}
	</div>

	{#if open}
		<!-- Inline rather than a popover, so it scrolls with the form and stays above the keyboard. -->
		<div class="rounded-xl border bg-muted/20 p-2" onkeydown={onPanelKeydown} role="presentation">
			<Input
				bind:value={query}
				bind:ref={searchEl}
				placeholder="Search icons…"
				aria-label="Search icons"
				onkeydown={onSearchKeydown}
			/>
			<div
				bind:this={gridEl}
				data-slot="icon-grid"
				role="group"
				aria-label="Icons"
				class="mt-2 grid max-h-56 grid-cols-[repeat(auto-fill,minmax(2.5rem,1fr))] gap-1 overflow-y-auto overscroll-contain"
			>
				{#each results as name, index (name)}
					{@const Glyph = TYPE_ICONS[name]}
					<button
						type="button"
						aria-label={name}
						aria-pressed={icon === name}
						onpointerenter={() => (hovered = name)}
						onpointerleave={() => (hovered = null)}
						onfocus={() => (hovered = name)}
						onblur={() => (hovered = null)}
						onkeydown={(event) => onGridKeydown(event, index)}
						class={cn(
							'flex size-10 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/30 focus-visible:outline-none sm:size-8',
							icon === name && 'bg-secondary text-foreground'
						)}
						onclick={() => {
							icon = name;
							setOpen(false);
						}}
					>
						<Glyph class="size-4" />
					</button>
				{/each}
			</div>
			<p
				data-testid="icon-name-readout"
				aria-live="polite"
				class="mt-2 h-5 truncate text-center text-xs text-muted-foreground"
			>
				{hovered ?? icon ?? ''}
			</p>
			{#if results.length === 0}
				<p class="py-4 text-center text-sm text-muted-foreground">No icons match "{query}".</p>
			{/if}
		</div>
	{/if}

	<div role="radiogroup" aria-label="Colour" class="flex flex-wrap gap-1.5">
		{#each TYPE_COLOUR_KEYS as key (key)}
			<button
				type="button"
				role="radio"
				aria-checked={colour === key}
				aria-label={label(key)}
				title={label(key)}
				class={cn(
					'size-6 rounded-full border-2 border-transparent transition-shadow focus-visible:ring-3 focus-visible:ring-ring/30 focus-visible:outline-none',
					colourClasses(key).swatch,
					colour === key && 'ring-2 ring-ring ring-offset-2 ring-offset-background'
				)}
				onclick={() => (colour = colour === key ? null : key)}
			></button>
		{/each}
	</div>
	{#if icon && !isKnownIcon(icon)}
		<p class="text-xs text-muted-foreground">
			This type uses an icon ("{icon}") that this version cannot draw, so it shows the generic one.
		</p>
	{/if}
</div>
