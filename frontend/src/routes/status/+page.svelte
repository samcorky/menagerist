<script lang="ts">
	import type { Component } from 'svelte';
	import { onMount } from 'svelte';
	import { SvelteMap } from 'svelte/reactivity';
	import { resolve } from '$app/paths';
	import {
		getHealthReady,
		getHealthReadyDetail,
		getVersion,
		getVersionDetail
	} from '$lib/api/client';
	import type {
		CheckObservation,
		ReadyDetailResponse,
		VersionDetailResponse,
		VersionResponse
	} from '$lib/api/client';
	import { auth } from '$lib/auth.svelte.js';
	import { LOGIN_PATH, STATUS_PATH } from '$lib/auth';
	import {
		countStatuses,
		formatObservedValue,
		readinessOf,
		readyDetailOf,
		type Readiness
	} from '$lib/status';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as PopoverTooltip from '$lib/components/ui/popover-tooltip/index.js';
	import {
		Activity,
		AlertTriangle,
		CheckCircle2,
		CircleX,
		Database,
		Gauge,
		GitBranch,
		HardDrive,
		LogIn,
		Network,
		PackageCheck,
		Pencil,
		RefreshCw,
		Server,
		ShieldCheck,
		TriangleAlert,
		Wrench
	} from '@lucide/svelte';

	function formatLabel(camel: string): string {
		return camel.replace(/([A-Z])/g, ' $1').replace(/^./, (s) => s.toUpperCase());
	}

	function formatGroup(key: string): string {
		return key.charAt(0).toUpperCase() + key.slice(1);
	}

	function formatValue(obs: CheckObservation): string {
		return formatObservedValue(obs.observedValue, obs.observedUnit);
	}

	function statusLabel(status: string): string {
		if (status === 'pass') return 'Operational';
		if (status === 'fail') return 'Degraded';
		return 'Warning';
	}

	function statusTone(status: string): string {
		if (status === 'pass') {
			return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400';
		}
		if (status === 'fail') {
			return 'border-destructive/30 bg-destructive/10 text-destructive';
		}
		return 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400';
	}

	function statusBarTone(status: string): string {
		if (status === 'pass') return 'border border-emerald-500/30 bg-emerald-500/10';
		if (status === 'fail') return 'border border-destructive/30 bg-destructive/10';
		return 'border border-amber-500/30 bg-amber-500/10';
	}

	function statusIcon(status: string): Component {
		if (status === 'pass') return CheckCircle2;
		if (status === 'fail') return CircleX;
		return TriangleAlert;
	}

	function groupIcon(key: string): Component {
		if (key === 'database') return Database;
		if (key === 'system') return Activity;
		if (key === 'pool') return Gauge;
		if (key === 'migration') return GitBranch;
		if (key === 'proxy') return Network;
		if (key === 'storage') return HardDrive;
		return Server;
	}

	function metricIcon(label: string): Component {
		const lower = label.toLowerCase();
		if (lower.includes('database') || lower.includes('db')) return Database;
		if (lower.includes('migration') || lower.includes('schema')) return GitBranch;
		if (lower.includes('pool') || lower.includes('connection')) return Gauge;
		if (lower.includes('storage') || lower.includes('space')) return HardDrive;
		if (lower.includes('writable')) return Pencil;
		if (lower.includes('version') || lower.includes('build')) return PackageCheck;
		if (lower.includes('health') || lower.includes('status')) return ShieldCheck;
		return Wrench;
	}

	function groupStatus(checks: Array<{ obs: CheckObservation }>): CheckObservation['status'] {
		if (checks.some(({ obs }) => obs.status === 'fail')) return 'fail';
		if (checks.some(({ obs }) => obs.status === 'warn')) return 'warn';
		return 'pass';
	}

	function groupSummary(checks: Array<{ obs: CheckObservation }>): string {
		const counts = countStatuses(checks.map(({ obs }) => obs));
		const parts: string[] = [];
		if (counts.pass > 0) parts.push(`${counts.pass}/${counts.total} Operational`);
		if (counts.warn > 0) {
			parts.push(`${counts.warn} warning${counts.warn === 1 ? '' : 's'}`);
		}
		if (counts.fail > 0) parts.push(`${counts.fail} alert${counts.fail === 1 ? '' : 's'}`);
		return parts.join(' · ') || 'No checks reported';
	}

	function urlSafeIdPart(value: string): string {
		return (
			value
				.normalize('NFKD')
				.replace(/[\u0300-\u036f]/g, '')
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, '-')
				.replace(/^-+|-+$/g, '') || 'check'
		);
	}

	function checkAnchorIds(
		groupKey: string,
		checks: Array<{ label: string; obs: CheckObservation }>
	): string[] {
		const baseIds = checks.map(({ label, obs }) => {
			const identity = [groupKey, label, obs.observedUnit ?? '']
				.map((part) => urlSafeIdPart(String(part)))
				.join('-');
			return `status-check-${identity}`;
		});
		const assignedIds: string[] = [];
		return baseIds.map((baseId, index) => {
			const isDuplicate = baseIds.filter((id) => id === baseId).length > 1;
			let id = isDuplicate ? `${baseId}-${index + 1}` : baseId;
			while (assignedIds.includes(id)) id = `${id}-${index + 1}`;
			assignedIds.push(id);
			return id;
		});
	}

	let highlightedCheckId = $state<string | null>(null);

	function clearStatusTarget(event: MouseEvent): void {
		if (event.target instanceof Element && event.target.closest('a[data-status-check-link]')) {
			return;
		}

		highlightedCheckId = null;
		if (
			document.activeElement instanceof HTMLElement &&
			document.activeElement.matches('.status-check-detail')
		) {
			document.activeElement.blur();
		}

		if (window.location.hash) {
			window.history.replaceState(
				window.history.state,
				'',
				`${window.location.pathname}${window.location.search}`
			);
		}
	}

	onMount(() => {
		document.addEventListener('click', clearStatusTarget);
		return () => document.removeEventListener('click', clearStatusTarget);
	});

	function latestObservationTime(report: ReadyDetailResponse): Date | null {
		let latest = Number.NEGATIVE_INFINITY;
		for (const observation of Object.values(report.checks).flat()) {
			const timestamp = Date.parse(observation.time);
			if (Number.isFinite(timestamp) && timestamp > latest) latest = timestamp;
		}
		return Number.isFinite(latest) ? new Date(latest) : null;
	}

	let readiness = $state<Readiness | null>(null);
	let detail = $state<ReadyDetailResponse | null>(null);
	let version = $state<VersionResponse | null>(null);
	let buildInfo = $state<VersionDetailResponse | null>(null);
	const showDetail = $derived(auth.signedIn && auth.can('system:diagnostics:read'));
	const signInHref = $derived(`${resolve(LOGIN_PATH)}?next=${encodeURIComponent(STATUS_PATH)}`);
	let loading = $state(true);
	let loadError = $state<string | null>(null);
	let lastCheckTime = $state<Date | null>(null);
	let refreshing = $state(false);
	let autoRefreshEnabled = $state(true);
	const autoRefreshMs = 30000;

	const groups = $derived.by(
		(): SvelteMap<string, Array<{ label: string; obs: CheckObservation }>> => {
			const map = new SvelteMap<string, Array<{ label: string; obs: CheckObservation }>>();
			if (!detail?.checks) return map;
			for (const [key, observations] of Object.entries(detail.checks)) {
				const [groupKey, metricName] = key.includes(':') ? key.split(':', 2) : ['other', key];
				if (!map.has(groupKey)) map.set(groupKey, []);
				for (const [index, obs] of observations.entries()) {
					const label = observations.length > 1 ? `${metricName} (${index + 1})` : metricName;
					map.get(groupKey)!.push({ label, obs });
				}
			}
			return map;
		}
	);

	const versionRows = $derived.by((): Array<{ label: string; value: string }> => {
		const rows: Array<{ label: string; value: string }> = [];
		const info = buildInfo;
		if (!info) return rows;

		rows.push({ label: 'Application', value: `${info.name} v${info.current_version}` });
		if (info.branch != null) rows.push({ label: 'Branch', value: info.branch });
		if (info.short_sha != null) {
			const dirty = info.dirty === true ? ' (dirty)' : '';
			rows.push({ label: 'Commit', value: `${info.short_sha}${dirty}` });
		}
		if (info.build_timestamp != null) {
			rows.push({ label: 'Built', value: new Date(info.build_timestamp).toLocaleString() });
		}
		rows.push({ label: 'Migration', value: info.migration_head.join(', ') || 'none' });

		return rows;
	});

	const healthSummary = $derived.by(() => {
		if (!detail?.checks) return countStatuses([]);
		return countStatuses(Object.values(detail.checks).flat());
	});

	async function load(refresh = false): Promise<void> {
		if (refresh) {
			refreshing = true;
		} else {
			loading = true;
		}
		loadError = null;

		try {
			const withDetail = showDetail;
			const [readyRes, versionRes, detailRes, buildRes] = await Promise.all([
				getHealthReady(),
				getVersion(),
				withDetail ? getHealthReadyDetail() : null,
				withDetail ? getVersionDetail() : null
			]);

			const state = readinessOf(readyRes);
			if (state === null || !versionRes.data) {
				throw new Error('The server gave an unexpected answer.');
			}
			readiness = state;
			version = versionRes.data;
			detail = detailRes ? readyDetailOf(detailRes) : null;
			buildInfo = buildRes?.data ?? null;
			lastCheckTime = (detail && latestObservationTime(detail)) || new Date();
		} catch (err) {
			loadError = err instanceof Error ? err.message : 'Unknown error';
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	$effect(() => {
		void load();
	});

	$effect(() => {
		if (!autoRefreshEnabled) return;
		const timer = window.setInterval(() => {
			void load(true);
		}, autoRefreshMs);
		return () => window.clearInterval(timer);
	});

	function formatTime(date: Date): string {
		return date.toLocaleString(undefined, {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}
</script>

<svelte:head>
	<title>System status - Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-5xl flex-col gap-6">
		<div
			class="flex items-start justify-between gap-4 rounded-2xl border border-border/70 bg-card/80 p-4 shadow-sm backdrop-blur-sm"
		>
			<div>
				<p class="mb-2 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
					Operations
				</p>
				<h1 class="font-heading text-3xl font-semibold tracking-tight">System status</h1>
				{#if lastCheckTime}
					<p class="mt-1 text-sm text-muted-foreground">
						Last checked at {formatTime(lastCheckTime)}
					</p>
				{/if}
				{#if version}
					<p class="mt-1 text-sm text-muted-foreground">
						{version.name} v{version.current_version}
					</p>
				{/if}
				<p class="mt-1 text-xs text-muted-foreground">
					{autoRefreshEnabled ? 'Auto-refreshing every 30s' : 'Auto-refresh paused'}
				</p>
			</div>
			<div class="flex items-center gap-2">
				{#if !auth.signedIn}
					<Button variant="outline" class="h-11" href={signInHref}>
						<LogIn class="size-4" />
						Sign in
					</Button>
				{/if}
				<Button
					variant="outline"
					size="icon"
					class="size-11"
					onclick={() => load(true)}
					disabled={refreshing || loading}
					aria-label="Refresh status"
					title="Refresh status"
				>
					<RefreshCw class="size-4 {refreshing ? 'animate-spin' : ''}" />
				</Button>
				<Button
					variant={autoRefreshEnabled ? 'default' : 'outline'}
					size="sm"
					onclick={() => (autoRefreshEnabled = !autoRefreshEnabled)}
					aria-label={autoRefreshEnabled ? 'Pause auto refresh' : 'Resume auto refresh'}
					title={autoRefreshEnabled ? 'Pause auto refresh' : 'Resume auto refresh'}
					class="min-h-11 gap-2 rounded-full"
				>
					<Activity class="size-4" />
					<span class="inline-flex items-center gap-1.5">
						<span
							class={autoRefreshEnabled
								? 'size-2 animate-pulse rounded-full bg-emerald-400 shadow-[0_0_0_4px_rgba(52,211,153,0.2)]'
								: 'size-2 rounded-full bg-muted-foreground'}
						></span>
						{autoRefreshEnabled ? 'Live' : 'Paused'}
					</span>
				</Button>
			</div>
		</div>

		{#if loading}
			<div class="flex flex-col gap-4">
				<div class="h-16 animate-pulse rounded-2xl bg-muted"></div>
				<div class="h-40 animate-pulse rounded-2xl bg-muted"></div>
				<div class="h-48 animate-pulse rounded-2xl bg-muted"></div>
			</div>
		{:else if loadError}
			<Card.Root class="border-destructive/50 bg-destructive/5 shadow-sm">
				<Card.Content class="px-5 py-4">
					<div class="flex items-center gap-2 text-destructive">
						<AlertTriangle class="size-4" />
						<p class="text-sm font-medium">Failed to load status</p>
					</div>
					<p class="mt-2 text-sm text-muted-foreground">{loadError}</p>
				</Card.Content>
			</Card.Root>
		{:else if readiness}
			{@const displayStatus = detail?.status ?? readiness}
			{@const isPass = displayStatus === 'pass'}
			{@const isWarning = displayStatus === 'warn'}
			{@const StatusIcon = statusIcon(displayStatus)}
			<Card.Root
				class={isPass
					? 'border-emerald-500/30 bg-emerald-500/5 shadow-sm'
					: isWarning
						? 'border-amber-500/30 bg-amber-500/5 shadow-sm'
						: 'border-destructive/30 bg-destructive/5 shadow-sm'}
			>
				<Card.Content class="flex items-center justify-between gap-3 px-5 py-4">
					<div class="flex items-center gap-3">
						<div
							class="flex size-8 items-center justify-center rounded-full {isPass
								? 'bg-emerald-500/10 text-emerald-600'
								: isWarning
									? 'bg-amber-500/10 text-amber-700 dark:text-amber-400'
									: 'bg-destructive/10 text-destructive'}"
						>
							<StatusIcon class="size-4" />
						</div>
						<div>
							<p class="font-medium">
								{isPass
									? 'All systems operational'
									: isWarning
										? 'Some checks need attention'
										: 'Service degraded'}
							</p>
							<p class="text-xs text-muted-foreground">
								{isPass
									? 'Everything Menagerist needs is working.'
									: isWarning
										? 'The service is ready, but one or more checks reported a warning.'
										: 'Something Menagerist needs is not working.'}
							</p>
						</div>
					</div>
					<Badge class={statusTone(displayStatus)}>
						<StatusIcon class="size-3" />
						{statusLabel(displayStatus)}
					</Badge>
				</Card.Content>
			</Card.Root>

			{#if detail}
				<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
					<div class="rounded-2xl border border-border/70 bg-card p-4 shadow-sm">
						<p class="text-xs tracking-[0.18em] text-muted-foreground uppercase">Checks</p>
						<div class="mt-2 flex items-baseline gap-2">
							<span class="font-heading text-2xl font-semibold">{healthSummary.total}</span>
							<span class="text-sm text-muted-foreground">total</span>
						</div>
					</div>
					<div class="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4 shadow-sm">
						<p class="text-xs tracking-[0.18em] text-emerald-700 uppercase dark:text-emerald-400">
							Healthy
						</p>
						<div class="mt-2 flex items-baseline gap-2 text-emerald-600 dark:text-emerald-400">
							<span class="font-heading text-2xl font-semibold">{healthSummary.pass}</span>
							<span class="text-sm">operational</span>
						</div>
					</div>
					<div class="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4 shadow-sm">
						<p class="text-xs tracking-[0.18em] text-amber-700 uppercase dark:text-amber-400">
							Warnings
						</p>
						<div class="mt-2 flex items-baseline gap-2 text-amber-600 dark:text-amber-400">
							<span class="font-heading text-2xl font-semibold">{healthSummary.warn}</span>
							<span class="text-sm">warning</span>
						</div>
					</div>
					<div class="rounded-2xl border border-destructive/20 bg-destructive/5 p-4 shadow-sm">
						<p class="text-xs tracking-[0.18em] text-destructive uppercase">Alerts</p>
						<div class="mt-2 flex items-baseline gap-2 text-destructive">
							<span class="font-heading text-2xl font-semibold">{healthSummary.fail}</span>
							<span class="text-sm">failing</span>
						</div>
					</div>
				</div>
			{/if}

			{#each groups as [groupKey, checks] (groupKey)}
				{@const anchorIds = checkAnchorIds(groupKey, checks)}
				{@const GroupIcon = groupIcon(groupKey)}
				{@const groupHealth = groupStatus(checks)}
				{@const GroupStatusIcon = statusIcon(groupHealth)}
				<Card.Root class="overflow-hidden border-border/70 bg-card shadow-sm">
					<Card.Header class="px-5 pt-5 pb-0">
						<div class="flex items-center justify-between gap-3">
							<div class="flex items-center gap-2.5">
								<div
									class="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground"
								>
									<GroupIcon class="size-4" />
								</div>
								<Card.Title class="text-base">{formatGroup(groupKey)}</Card.Title>
							</div>
							<Badge class={statusTone(groupHealth)}>
								<GroupStatusIcon class="size-3" />
								{statusLabel(groupHealth)}
							</Badge>
						</div>
					</Card.Header>
					<div class="space-y-2 px-5 pt-3 pb-0">
						<div
							class="flex h-3 gap-1"
							role="group"
							aria-label={`${formatGroup(groupKey)} checks; select a segment to view its details`}
						>
							{#each checks as { label, obs }, index (`${label}-${index}`)}
								<PopoverTooltip.Root>
									<PopoverTooltip.Trigger>
										{#snippet child({ props })}
											<a
												{...props}
												data-status-check-link
												href={`#${anchorIds[index]}`}
												onclick={() => (highlightedCheckId = anchorIds[index])}
												class="min-w-0 flex-1 rounded-full {statusBarTone(
													obs.status
												)} transition-[filter] duration-150 hover:brightness-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none"
												aria-label={`${formatLabel(label)}: ${statusLabel(obs.status)}. ${formatValue(obs)}${obs.output ? `. ${obs.output}` : ''}`}
											></a>
										{/snippet}
									</PopoverTooltip.Trigger>
									<PopoverTooltip.Content class="text-left whitespace-normal">
										{formatLabel(label)}: {statusLabel(obs.status)}. {formatValue(obs)}
										{#if obs.output}
											. {obs.output}
										{/if}
									</PopoverTooltip.Content>
								</PopoverTooltip.Root>
							{/each}
						</div>
						<p class="text-center text-xs font-medium text-muted-foreground">
							{groupSummary(checks)}
						</p>
					</div>
					<Card.Content class="space-y-3 p-4">
						{#each checks as { label, obs }, index (`${label}-${index}`)}
							{@const MetricIcon = metricIcon(label)}
							{@const MetricStatusIcon = statusIcon(obs.status)}
							<div
								id={anchorIds[index]}
								tabindex="-1"
								class="status-check-detail flex scroll-mt-24 items-start gap-3 rounded-xl border border-border/70 bg-muted/30 px-3 py-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring {highlightedCheckId ===
								anchorIds[index]
									? 'status-check-highlighted'
									: ''}"
							>
								<div
									class="flex size-8 shrink-0 items-center justify-center rounded-md bg-background text-muted-foreground ring-1 ring-border/80"
								>
									<MetricIcon class="size-4" />
								</div>
								<div class="min-w-0 flex-1">
									<div class="flex items-center justify-between gap-3">
										<span class="text-sm font-medium">{formatLabel(label)}</span>
										<Badge class={statusTone(obs.status)}>
											<MetricStatusIcon class="size-3" />
											{statusLabel(obs.status)}
										</Badge>
									</div>
									<p class="mt-1 font-mono text-xs text-muted-foreground">{formatValue(obs)}</p>
									{#if obs.output}
										<p
											class={obs.status === 'warn'
												? 'mt-2 text-sm leading-relaxed break-words text-amber-700 dark:text-amber-400'
												: 'mt-2 text-sm leading-relaxed break-words text-destructive'}
										>
											{obs.output}
										</p>
									{/if}
								</div>
							</div>
						{/each}
					</Card.Content>
				</Card.Root>
			{/each}

			{#if buildInfo}
				<Card.Root class="overflow-hidden border-border/70 bg-card shadow-sm">
					<Card.Header class="px-5 pt-5 pb-0">
						<div class="flex items-center gap-2.5">
							<div
								class="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground"
							>
								<PackageCheck class="size-4" />
							</div>
							<Card.Title class="text-base">Build info</Card.Title>
						</div>
					</Card.Header>
					<Card.Content class="space-y-0 p-0">
						{#each versionRows as { label, value }, i (label)}
							<div
								class="flex items-center justify-between gap-4 px-5 py-3 {i !==
								versionRows.length - 1
									? 'border-b border-border/80'
									: ''}"
							>
								<span class="text-sm text-muted-foreground">{label}</span>
								<span class="max-w-[60%] truncate text-right font-mono text-sm">{value}</span>
							</div>
						{/each}
					</Card.Content>
				</Card.Root>
			{/if}
		{/if}
	</div>
</main>

<style>
	.status-check-detail.status-check-highlighted {
		outline: 2px solid var(--color-ring);
		outline-offset: 2px;
		animation: status-check-arrive 1.2s ease-out;
	}

	@keyframes status-check-arrive {
		from {
			box-shadow: 0 0 0 6px color-mix(in oklab, var(--color-ring) 35%, transparent);
		}

		to {
			box-shadow: 0 0 0 0 transparent;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.status-check-detail.status-check-highlighted {
			animation: none;
		}
	}
</style>
