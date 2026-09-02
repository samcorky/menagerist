<script lang="ts">
	import type { Component } from 'svelte';
	import { SvelteMap } from 'svelte/reactivity';
	import { getVersion } from '$lib/api/client';
	import type { CheckObservation, ReadyResponse, VersionResponse } from '$lib/api/client';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import {
		Activity,
		AlertTriangle,
		CheckCircle2,
		CircleX,
		Database,
		Gauge,
		GitBranch,
		PackageCheck,
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
		if (obs.observedUnit === 'percent') return `${obs.observedValue}%`;
		if (obs.observedUnit === 'ms') return `${obs.observedValue} ms`;
		return String(obs.observedValue);
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
		return Server;
	}

	function metricIcon(label: string): Component {
		const lower = label.toLowerCase();
		if (lower.includes('database') || lower.includes('db')) return Database;
		if (lower.includes('migration') || lower.includes('schema')) return GitBranch;
		if (lower.includes('pool') || lower.includes('connection')) return Gauge;
		if (lower.includes('version') || lower.includes('build')) return PackageCheck;
		if (lower.includes('health') || lower.includes('status')) return ShieldCheck;
		return Wrench;
	}

	let ready = $state<ReadyResponse | null>(null);
	let version = $state<VersionResponse | null>(null);
	let loading = $state(true);
	let loadError = $state<string | null>(null);
	let lastChecked = $state<Date | null>(null);
	let refreshing = $state(false);
	let autoRefreshEnabled = $state(true);
	const autoRefreshMs = 30000;

	const groups = $derived.by(
		(): SvelteMap<string, Array<{ label: string; obs: CheckObservation }>> => {
			const map = new SvelteMap<string, Array<{ label: string; obs: CheckObservation }>>();
			if (!ready?.checks) return map;
			for (const [key, obs] of Object.entries(ready.checks)) {
				const [groupKey, metricName] = key.includes(':') ? key.split(':', 2) : ['other', key];
				if (!map.has(groupKey)) map.set(groupKey, []);
				map.get(groupKey)!.push({ label: metricName, obs });
			}
			return map;
		}
	);

	const versionRows = $derived.by((): Array<{ label: string; value: string }> => {
		const rows: Array<{ label: string; value: string }> = [];
		if (!version) return rows;

		rows.push({
			label: 'Application',
			value: `menagerist v${version.current_version}`
		});

		if (version.branch != null) {
			rows.push({ label: 'Branch', value: version.branch });
		}

		if (version.short_sha != null) {
			const dirty = version.dirty === true ? ' (dirty)' : '';
			rows.push({ label: 'Commit', value: `${version.short_sha}${dirty}` });
		}

		if (version.build_timestamp != null) {
			rows.push({
				label: 'Built',
				value: new Date(version.build_timestamp).toLocaleString()
			});
		}

		rows.push({
			label: 'Migration',
			value: version.migration_head.join(', ') || 'none'
		});

		return rows;
	});

	async function load(refresh = false): Promise<void> {
		if (refresh) {
			refreshing = true;
		} else {
			loading = true;
		}
		loadError = null;

		try {
			const [readyRes, versionRes] = await Promise.all([
				fetch('/api/health/ready'),
				getVersion({ throwOnError: true })
			]);

			ready = (await readyRes.json()) as ReadyResponse;
			version = versionRes.data as VersionResponse;
			lastChecked = new Date();
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
		return date.toLocaleTimeString(undefined, {
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}
</script>

<svelte:head>
	<title>System Status — Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-3xl flex-col gap-6">
		<div class="flex items-start justify-between gap-4">
			<div>
				<p class="mb-2 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
					Operations
				</p>
				<h1 class="font-heading text-3xl font-semibold tracking-tight">System Status</h1>
				{#if lastChecked}
					<p class="mt-1 text-sm text-muted-foreground">
						Last checked at {formatTime(lastChecked)}
					</p>
				{/if}
				<p class="mt-1 text-xs text-muted-foreground">
					{autoRefreshEnabled ? 'Auto-refreshing every 30s' : 'Auto-refresh paused'}
				</p>
			</div>
			<div class="flex items-center gap-2">
				<Button
					variant="outline"
					size="sm"
					onclick={() => load(true)}
					disabled={refreshing || loading}
					class="gap-2"
				>
					<RefreshCw class="size-4 {refreshing ? 'animate-spin' : ''}" />
					Refresh
				</Button>
				<Button
					variant={autoRefreshEnabled ? 'default' : 'outline'}
					size="sm"
					onclick={() => (autoRefreshEnabled = !autoRefreshEnabled)}
					class="min-w-[7rem]"
				>
					{autoRefreshEnabled ? 'Pause auto' : 'Resume auto'}
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
		{:else if ready}
			{@const isPass = ready.status === 'pass'}
			{@const StatusIcon = statusIcon(ready.status)}
			<Card.Root
				class={isPass
					? 'border-emerald-500/30 bg-emerald-500/5 shadow-sm'
					: 'border-destructive/30 bg-destructive/5 shadow-sm'}
			>
				<Card.Content class="flex items-center justify-between gap-3 px-5 py-4">
					<div class="flex items-center gap-3">
						<div
							class="flex size-8 items-center justify-center rounded-full {isPass
								? 'bg-emerald-500/10 text-emerald-600'
								: 'bg-destructive/10 text-destructive'}"
						>
							<StatusIcon class="size-4" />
						</div>
						<div>
							<p class="font-medium">{isPass ? 'All systems operational' : 'Service degraded'}</p>
							<p class="text-xs text-muted-foreground">
								{isPass
									? 'No checks are failing right now.'
									: 'At least one health check is failing.'}
							</p>
						</div>
					</div>
					<Badge class={statusTone(ready.status)}>
						<StatusIcon class="size-3" />
						{statusLabel(ready.status)}
					</Badge>
				</Card.Content>
			</Card.Root>

			{#each groups as [groupKey, checks] (groupKey)}
				{@const GroupIcon = groupIcon(groupKey)}
				{@const groupPass = checks.every((c) => c.obs.status === 'pass')}
				{@const GroupStatusIcon = statusIcon(groupPass ? 'pass' : 'fail')}
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
							<Badge class={statusTone(groupPass ? 'pass' : 'fail')}>
								<GroupStatusIcon class="size-3" />
								{groupPass ? 'Operational' : 'Degraded'}
							</Badge>
						</div>
					</Card.Header>
					<div class="px-5 pt-3 pb-0">
						<div
							class="rounded-full border border-border/80 bg-muted/50 px-2.5 py-1 text-center text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase"
						>
							{checks.filter((c) => c.obs.status === 'pass').length}/{checks.length} passing
						</div>
					</div>
					<Card.Content class="space-y-3 p-4">
						{#each checks as { label, obs } (label)}
							{@const checkPass = obs.status === 'pass'}
							{@const MetricIcon = metricIcon(label)}
							{@const MetricStatusIcon = statusIcon(checkPass ? 'pass' : 'fail')}
							<div
								class="flex items-start gap-3 rounded-xl border border-border/70 bg-muted/30 px-3 py-3"
							>
								<div
									class="flex size-8 shrink-0 items-center justify-center rounded-md bg-background text-muted-foreground ring-1 ring-border/80"
								>
									<MetricIcon class="size-4" />
								</div>
								<div class="min-w-0 flex-1">
									<div class="flex items-center justify-between gap-3">
										<span class="text-sm font-medium">{formatLabel(label)}</span>
										<Badge class={statusTone(checkPass ? 'pass' : 'fail')}>
											<MetricStatusIcon class="size-3" />
											{checkPass ? 'Operational' : 'Degraded'}
										</Badge>
									</div>
									<div class="mt-1 flex items-center gap-2 font-mono text-xs text-muted-foreground">
										<span>{formatValue(obs)}</span>
										{#if obs.output}
											<span class="text-destructive">• {obs.output}</span>
										{/if}
									</div>
								</div>
							</div>
						{/each}
					</Card.Content>
				</Card.Root>
			{/each}

			{#if version}
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
