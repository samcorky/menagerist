<script lang="ts">
	import { Collapsible as CollapsiblePrimitive } from 'bits-ui';
	import { cn } from '$lib/utils.js';

	// `animated` folds the height open and shut. A section that starts open passes false until the
	// person first toggles it, so it is simply there instead of dropping down on every render.
	let {
		ref = $bindable(null),
		class: className,
		animated = true,
		...restProps
	}: CollapsiblePrimitive.ContentProps & { animated?: boolean } = $props();
</script>

<CollapsiblePrimitive.Content
	bind:ref
	data-slot="collapsible-content"
	class={cn(
		animated &&
			'overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down motion-reduce:animate-none',
		className
	)}
	{...restProps}
/>
