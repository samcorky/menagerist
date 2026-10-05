<script lang="ts">
	import { Input } from '$lib/components/ui/input/index.js';
	import { formatPartialDate } from '$lib/format-date';
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let {
		value,
		onChange,
		ariaLabel,
		prop: _prop
	}: {
		value: unknown;
		onChange: (v: unknown) => void;
		ariaLabel: string;
		prop: JsonSchemaProperty;
	} = $props();

	let text = $derived(typeof value === 'string' || typeof value === 'number' ? String(value) : '');
	let preview = $derived.by(() => {
		if (!/^\d{4}(-\d{2}){0,2}$/.test(text)) return '';
		const formatted = formatPartialDate(text, 'long');
		return formatted === text ? '' : formatted;
	});
</script>

<div class="flex-1">
	<Input
		type="text"
		value={text}
		oninput={(e) => onChange((e.target as HTMLInputElement).value)}
		placeholder="YYYY, YYYY-MM or YYYY-MM-DD"
		class="w-full"
		aria-label={ariaLabel}
	/>
	<p class="mt-1 min-h-4 text-xs text-muted-foreground" aria-live="polite">{preview}</p>
</div>
