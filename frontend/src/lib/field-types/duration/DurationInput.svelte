<script lang="ts">
	import { untrack } from 'svelte';
	import { Input } from '$lib/components/ui/input/index.js';
	import { readPropMeta } from '$lib/schema-meta';
	import type { JsonSchemaProperty } from '$lib/schema-types';
	import { durationSeconds, formatDuration, parseDuration, type DurationStyle } from './format';

	let {
		value,
		onChange,
		ariaLabel,
		prop
	}: {
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	} = $props();

	let style = $derived<DurationStyle>(readPropMeta(prop).display === 'words' ? 'words' : 'clock');

	function toText(v: unknown, s: DurationStyle): string {
		const seconds = durationSeconds(v);
		if (seconds !== null) return formatDuration(seconds, s);
		return typeof v === 'string' ? v : '';
	}

	let draft = $state(untrack(() => toText(value, style)));

	// Re-sync only when the value changes to something the draft does not already represent.
	$effect(() => {
		const v = value;
		const current = untrack(() => draft);
		if (typeof v === 'string' && v === current) return;
		const incoming = durationSeconds(v);
		if (incoming !== null && incoming === parseDuration(current)) return;
		if (incoming === null && v === '' && parseDuration(current) === null && current === '') return;
		draft = toText(
			v,
			untrack(() => style)
		);
	});

	function onInput(e: Event) {
		draft = (e.target as HTMLInputElement).value;
		if (draft.trim() === '') return onChange('');
		const seconds = parseDuration(draft);
		onChange(seconds === null ? draft : String(seconds));
	}

	function onBlur() {
		const seconds = parseDuration(draft);
		if (seconds !== null) draft = formatDuration(seconds, style);
	}
</script>

<Input
	type="text"
	value={draft}
	oninput={onInput}
	onblur={onBlur}
	placeholder="m:ss or h:mm:ss"
	class="flex-1"
	aria-label={ariaLabel}
/>
