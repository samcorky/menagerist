<script lang="ts">
	import {
		avatarPixels,
		avatarTone,
		avatarUrl,
		initialsFor,
		toneClasses,
		type AvatarSize
	} from '$lib/avatars/avatar';
	import { cn } from '$lib/utils.js';

	type Props = {
		userId: string;
		displayName: string;
		avatarVersion?: string | null;
		size?: AvatarSize;
		/** The name is printed beside the picture, so it adds nothing for a screen reader. */
		decorative?: boolean;
		class?: string;
	};

	let {
		userId,
		displayName,
		avatarVersion = null,
		size = 'md',
		decorative = false,
		class: className
	}: Props = $props();

	const pixels = $derived(avatarPixels(size));
	const src = $derived(avatarVersion ? avatarUrl(userId, avatarVersion, pixels.load) : null);
	// A picture that fails to load falls back to the initials, until the address changes.
	let failedSrc = $state<string | null>(null);
	const showImage = $derived(src !== null && src !== failedSrc);
	const textSize = $derived(
		size === 'xl'
			? 'text-3xl'
			: size === 'lg'
				? 'text-sm'
				: size === 'md'
					? 'text-xs'
					: 'text-[0.625rem]'
	);
</script>

<span
	class={cn(
		'inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full select-none',
		// Also the placeholder while a picture loads.
		toneClasses(avatarTone(userId)),
		className
	)}
	style:width="{pixels.shown}px"
	style:height="{pixels.shown}px"
	role={decorative || showImage ? undefined : 'img'}
	aria-label={decorative || showImage ? undefined : displayName}
	aria-hidden={decorative ? 'true' : undefined}
	data-testid="user-avatar"
>
	{#if showImage && src}
		<img
			{src}
			alt={decorative ? '' : displayName}
			width={pixels.shown}
			height={pixels.shown}
			class="size-full object-cover"
			loading="lazy"
			decoding="async"
			onerror={() => (failedSrc = src)}
		/>
	{:else}
		<span class={cn('leading-none font-semibold', textSize)} aria-hidden="true">
			{initialsFor(displayName)}
		</span>
	{/if}
</span>
