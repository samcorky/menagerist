<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/json-schema';
	import { cronMode } from './cron-mode.svelte';
	import { explainCron } from './explain';
	import { useSchedulePreview } from '$lib/schedule-preview.svelte';

	let { value, prop: _prop }: { value: unknown; prop: JsonSchemaProperty } = $props();

	let text = $derived(typeof value === 'string' ? value.trim() : '');
	let reading = $derived(explainCron(text));
	const preview = useSchedulePreview(() => text);
</script>

<span class="flex min-w-0 flex-col gap-0.5">
	{#if !reading.ok}
		<code class="font-mono text-sm break-all">{text}</code>
		<span class="text-xs text-muted-foreground">{reading.reason}</span>
	{:else if text === ''}
		<span>Off</span>
	{:else if cronMode.value === 'cron'}
		<code class="font-mono text-sm break-all">{text}</code>
		<span class="text-xs text-muted-foreground">{reading.text}</span>
	{:else}
		<span>{reading.text}</span>
		<code class="font-mono text-xs break-all text-muted-foreground">{text}</code>
	{/if}
	{#if preview.state.status === 'ready' && preview.state.runs}
		<span class="text-xs text-muted-foreground" title={preview.state.runs.timezone}
			>Next run: {preview.state.runs.next}</span
		>
	{/if}
</span>
