<script lang="ts">
	import { untrack } from 'svelte';
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { TimeField } from '$lib/components/ui/time-field/index.js';
	import { NativeSelect, NativeSelectOption } from '$lib/components/ui/native-select/index.js';
	import type { JsonSchemaProperty } from '$lib/json-schema';
	import {
		SENTENCE_KINDS,
		MINUTE_STEPS,
		WEEKDAYS,
		buildCron,
		formatTime,
		ordinal,
		parseCron,
		parseTime,
		switchKind,
		type Sentence,
		type SentenceKind
	} from './builder';
	import { cronMode } from './cron-mode.svelte';
	import { explainCron } from './explain';
	import { useSchedulePreview } from '$lib/schedule-preview.svelte';

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

	const uid = $props.id();
	const helpId = `${uid}-help`;

	let text = $derived(typeof value === 'string' ? value : '');
	let sentence = $derived(parseCron(text));
	let reading = $derived(explainCron(text));

	const preview = useSchedulePreview(() => text);

	// Errors stay muted until the user has left the control once, unless already unreadable on load.
	let touched = $state(false);
	const unreadableOnLoad = untrack(() => !explainCron(text).ok);
	let showError = $derived(touched || unreadableOnLoad);

	const MINUTES = Array.from({ length: 60 }, (_, i) => i);
	const MONTH_DAYS = Array.from({ length: 28 }, (_, i) => i + 1);

	type Timed = Extract<Sentence, { hour: number }>;

	function emit(next: Sentence): void {
		onChange(buildCron(next));
	}

	function changeKind(kind: SentenceKind): void {
		emit(switchKind(sentence, kind));
	}

	function changeTime(s: Timed, raw: string): void {
		const t = parseTime(raw);
		if (t) emit({ ...s, hour: t.hour, minute: t.minute });
	}
</script>

{#snippet timeInput(s: Timed)}
	<TimeField
		value={formatTime(s.hour, s.minute)}
		onValueChange={(v) => v && changeTime(s, v)}
		onfocusout={() => (touched = true)}
		aria-label="{ariaLabel}: time"
	/>
{/snippet}

<div class="flex min-w-0 flex-1 flex-col gap-2">
	<div role="group" aria-label="Show schedule as" class="flex gap-1">
		<Button
			type="button"
			variant={cronMode.value === 'words' ? 'secondary' : 'outline'}
			size="sm"
			class="min-h-11"
			aria-pressed={cronMode.value === 'words'}
			onclick={() => cronMode.set('words')}>In words</Button
		>
		<Button
			type="button"
			variant={cronMode.value === 'cron' ? 'secondary' : 'outline'}
			size="sm"
			class="min-h-11"
			aria-pressed={cronMode.value === 'cron'}
			onclick={() => cronMode.set('cron')}>Cron</Button
		>
	</div>

	{#if cronMode.value === 'words'}
		{#if sentence}
			<div class="flex flex-wrap items-center gap-2">
				<NativeSelect
					value={sentence.kind}
					onchange={(e) => changeKind(e.currentTarget.value as SentenceKind)}
					onblur={() => (touched = true)}
					class="min-h-11 w-auto"
					aria-label="{ariaLabel}: how often"
				>
					{#each SENTENCE_KINDS as k (k.kind)}
						<NativeSelectOption value={k.kind}>{k.label}</NativeSelectOption>
					{/each}
				</NativeSelect>

				{#if sentence.kind === 'minutes'}
					{@const s = sentence}
					<NativeSelect
						value={String(s.every)}
						onchange={(e) => emit({ ...s, every: Number(e.currentTarget.value) as typeof s.every })}
						onblur={() => (touched = true)}
						class="min-h-11 w-auto"
						aria-label="{ariaLabel}: minutes between runs"
					>
						{#each MINUTE_STEPS as n (n)}
							<NativeSelectOption value={String(n)}>Every {n} minutes</NativeSelectOption>
						{/each}
					</NativeSelect>
				{:else if sentence.kind === 'hourly'}
					{@const s = sentence}
					<NativeSelect
						value={String(s.minute)}
						onchange={(e) => emit({ ...s, minute: Number(e.currentTarget.value) })}
						onblur={() => (touched = true)}
						class="min-h-11 w-auto"
						aria-label="{ariaLabel}: minute of the hour"
					>
						{#each MINUTES as n (n)}
							<NativeSelectOption value={String(n)}
								>{n === 0 ? 'On the hour' : `${n} minutes past the hour`}</NativeSelectOption
							>
						{/each}
					</NativeSelect>
				{:else if sentence.kind === 'daily' || sentence.kind === 'weekdays'}
					{@render timeInput(sentence)}
				{:else if sentence.kind === 'weekly'}
					{@const s = sentence}
					<NativeSelect
						value={String(s.day)}
						onchange={(e) => emit({ ...s, day: Number(e.currentTarget.value) })}
						onblur={() => (touched = true)}
						class="min-h-11 w-auto"
						aria-label="{ariaLabel}: day of the week"
					>
						{#each WEEKDAYS as d (d.value)}
							<NativeSelectOption value={String(d.value)}>{d.label}</NativeSelectOption>
						{/each}
					</NativeSelect>
					{@render timeInput(s)}
				{:else if sentence.kind === 'monthly'}
					{@const s = sentence}
					<NativeSelect
						value={String(s.dayOfMonth)}
						onchange={(e) => emit({ ...s, dayOfMonth: Number(e.currentTarget.value) })}
						onblur={() => (touched = true)}
						class="min-h-11 w-auto"
						aria-label="{ariaLabel}: day of the month"
					>
						{#each MONTH_DAYS as n (n)}
							<NativeSelectOption value={String(n)}>On the {ordinal(n)}</NativeSelectOption>
						{/each}
					</NativeSelect>
					{@render timeInput(s)}
				{/if}
			</div>
		{:else}
			<div
				class="flex flex-col items-start gap-2 rounded-xl bg-muted p-3 text-sm text-muted-foreground"
			>
				<p class="font-medium text-foreground">This schedule is custom.</p>
				<p>
					{reading.ok ? reading.text : reading.reason}
					<code class="font-mono text-xs break-all">{text}</code>
				</p>
				<Button
					type="button"
					variant="outline"
					size="sm"
					class="min-h-11"
					onclick={() => cronMode.set('cron')}>Edit as cron</Button
				>
			</div>
		{/if}
	{:else}
		<Input
			value={text}
			oninput={(e) => onChange(e.currentTarget.value)}
			onblur={() => (touched = true)}
			class="min-h-11 font-mono"
			autocomplete="off"
			spellcheck={false}
			placeholder="0 3 * * *"
			aria-label={ariaLabel}
			aria-describedby={helpId}
		/>
		<p id={helpId} class="text-xs text-muted-foreground">
			Five parts: minute, hour, day of month, month, day of week. Leave it empty to turn it off.
		</p>
	{/if}

	<div aria-live="polite" class="flex flex-col gap-1 text-sm">
		<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
			{#if reading.ok}
				<span>{reading.text}</span>
				{#if text.trim() !== ''}
					<code class="font-mono text-xs break-all text-muted-foreground">{text}</code>
				{/if}
			{:else}
				<span
					class={showError ? 'flex items-center gap-1.5 text-destructive' : 'text-muted-foreground'}
				>
					{#if showError}<CircleAlertIcon class="size-4 shrink-0" aria-hidden="true" />{/if}
					{reading.reason}
				</span>
				<code class="font-mono text-xs break-all text-muted-foreground">{text}</code>
			{/if}
		</div>
		{#if preview.state.status === 'off'}
			<p>It will not run.</p>
		{:else if preview.state.status === 'error'}
			<p class="text-xs text-muted-foreground">Could not work out the next run.</p>
		{:else if preview.state.status === 'ready' || preview.state.status === 'loading'}
			{@const runs = preview.state.status === 'ready' ? preview.state.runs : preview.state.previous}
			{#if runs}
				<div class={preview.state.status === 'loading' ? 'text-muted-foreground' : ''}>
					<p>
						Next run: {runs.next}
						<span class="text-xs text-muted-foreground">({runs.timezone})</span>
					</p>
					{#if runs.later.length > 0}
						<p class="text-xs text-muted-foreground">Then {runs.later.join(' · ')}</p>
					{/if}
				</div>
			{/if}
		{/if}
	</div>
</div>
