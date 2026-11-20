<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';
	import { Input } from '$lib/components/ui/input/index.js';

	// A text input with the browser's own suggestions: a native <datalist>. The browser shows and
	// filters them its usual way (a list on desktop, chips above the keyboard on Android), with
	// keyboard and screen reader support, and a click elsewhere can never pick one (#680).
	let {
		value,
		suggestions,
		oninput,
		...rest
	}: Omit<HTMLInputAttributes, 'value' | 'oninput' | 'list' | 'type' | 'files'> & {
		value: string;
		/** Offered most useful first; the browser narrows them to what was typed. */
		suggestions: readonly string[];
		oninput: (value: string) => void;
	} = $props();

	const listId = $props.id();
</script>

<Input
	{...rest}
	{value}
	list={suggestions.length > 0 ? listId : undefined}
	autocomplete="off"
	oninput={(e) => oninput(e.currentTarget.value)}
/>
{#if suggestions.length > 0}
	<datalist id={listId}>
		{#each suggestions as suggestion (suggestion)}
			<option value={suggestion}></option>
		{/each}
	</datalist>
{/if}
