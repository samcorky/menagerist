<script lang="ts">
	import { ExternalLink, RefreshCw, Rocket } from '@lucide/svelte';
	import type { ReleaseResponse } from '$lib/api/client';
	import { formatDateTime } from '$lib/format-date';
	import { releaseViewOf, type ReleaseTone } from '$lib/status';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';

	let {
		release,
		canCheck,
		checking,
		checkError,
		onCheck
	}: {
		release: ReleaseResponse;
		canCheck: boolean;
		checking: boolean;
		checkError: string | null;
		onCheck: () => void;
	} = $props();

	const view = $derived(releaseViewOf(release));

	const toneClass: Record<ReleaseTone, string> = {
		ok: 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400',
		attention: 'border-amber-500/50 text-amber-600 dark:text-amber-400',
		neutral: 'text-muted-foreground'
	};
</script>

<Card.Root class="overflow-hidden border-border/70 bg-card shadow-sm">
	<Card.Header class="px-5 pt-5 pb-0">
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div class="flex items-center gap-2.5">
				<div
					class="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground"
				>
					<Rocket class="size-4" />
				</div>
				<Card.Title class="text-base">Updates</Card.Title>
			</div>
			<Badge variant="outline" class={toneClass[view.tone]}>{view.badge}</Badge>
		</div>
	</Card.Header>
	<Card.Content class="space-y-3 px-0 pb-0">
		<p class="px-5 text-sm">{view.summary}</p>
		{#if view.failureNote}
			<p role="status" class="px-5 text-sm text-amber-600 dark:text-amber-400">
				{view.failureNote}
				{#if release.checked_at}The last good result is shown.{/if}
			</p>
		{/if}
		<div>
			{#each view.rows as row (row.label)}
				<div class="flex items-center justify-between gap-4 border-t border-border/80 px-5 py-3">
					<span class="text-sm text-muted-foreground">{row.label}</span>
					{#if row.time}
						{@const when = formatDateTime(row.value)}
						<span class="text-right text-sm" title={when.utc}>{when.local}</span>
					{:else}
						<span class="max-w-[60%] truncate text-right font-mono text-sm">{row.value}</span>
					{/if}
				</div>
			{/each}
		</div>
		{#if checkError}
			<p role="alert" class="px-5 text-sm text-destructive">{checkError}</p>
		{/if}
		{#if view.notesUrl || canCheck}
			<div class="flex flex-wrap gap-2 border-t border-border/80 px-5 py-4">
				{#if canCheck}
					<Button variant="outline" class="h-11" disabled={checking} onclick={onCheck}>
						<RefreshCw class="size-4 {checking ? 'animate-spin motion-reduce:animate-none' : ''}" />
						{checking ? 'Checking...' : 'Check now'}
					</Button>
				{/if}
				{#if view.notesUrl}
					<Button
						variant="ghost"
						class="h-11"
						href={view.notesUrl}
						target="_blank"
						rel="noopener noreferrer"
					>
						<ExternalLink class="size-4" />
						Release notes
						<span class="sr-only"> (opens in a new tab)</span>
					</Button>
				{/if}
			</div>
		{/if}
	</Card.Content>
</Card.Root>
