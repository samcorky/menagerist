<script lang="ts">
	import { Package } from '@lucide/svelte';
	import { TYPE_ICONS } from '$lib/type-icons';
	import { colourClasses, isKnownIcon } from '$lib/type-appearance';
	import { cn } from '$lib/utils.js';

	// An item type's icon in its colour. A type with no icon, or one this version cannot draw,
	// shows the generic package icon, so a cover-less item and an untyped one still look right.
	let {
		icon,
		colour,
		boxed = false,
		class: className
	}: {
		icon?: string | null;
		colour?: string | null;
		/** Sits on a tinted square, as a tile placeholder or a list marker. */
		boxed?: boolean;
		class?: string;
	} = $props();

	const Icon = $derived(isKnownIcon(icon) ? TYPE_ICONS[icon] : Package);
	const classes = $derived(colourClasses(colour));
</script>

<span
	aria-hidden="true"
	data-slot="type-icon"
	data-icon={icon ?? ''}
	data-colour={colour ?? ''}
	class={cn(
		'inline-flex shrink-0 items-center justify-center',
		classes.text,
		boxed && ['rounded-lg', classes.background],
		className
	)}
>
	<Icon class="size-[1em]" />
</span>
