<script lang="ts">
	import { untrack } from 'svelte';
	import { resolve } from '$app/paths';
	import { toast } from 'svelte-sonner';
	import { ChevronDown } from '@lucide/svelte';
	import {
		listJobRuns,
		listJobs,
		runJobNow,
		type JobResponse,
		type JobRunResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { auth } from '$lib/auth.svelte.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import { formatDateTime } from '$lib/format-date';
	import {
		isActive,
		nextRunLabel,
		runDuration,
		runStatusLabel,
		runTone,
		startedByHand,
		type RunStatus
	} from '$lib/scheduled-tasks';
	import BackButton from '$lib/components/back-button.svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge, type BadgeVariant } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Collapsible from '$lib/components/ui/collapsible/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	type History = {
		open: boolean;
		loading: boolean;
		error: string | null;
		runs: JobRunResponse[] | null;
	};

	const POLL_BUSY_MS = 3000;
	const POLL_IDLE_MS = 30000;
	const HISTORY_LIMIT = 10;

	let jobs = $state<JobResponse[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let starting = $state<string | null>(null);
	let history = $state<Record<string, History>>({});
	let announcement = $state('');

	const loadingDisplay = delayedLoading();
	$effect(() => {
		loadingDisplay.set(loading);
	});

	const canRead = $derived(auth.can('scheduling:job:read'));
	const canRun = $derived(auth.can('scheduling:job:run'));
	const anyActive = $derived(jobs.some((j) => j.active_run && isActive(j.active_run.status)));

	function badgeVariant(status: RunStatus): BadgeVariant {
		const tone = runTone(status);
		if (tone === 'working') return 'secondary';
		if (tone === 'bad') return 'destructive';
		return 'outline';
	}

	function formatWhen(iso: string): string {
		return formatDateTime(iso).local;
	}

	function activeRun(job: JobResponse): JobRunResponse | null {
		return job.active_run && isActive(job.active_run.status) ? job.active_run : null;
	}

	async function loadHistory(jobKey: string) {
		const current = history[jobKey];
		history[jobKey] = {
			open: current?.open ?? true,
			loading: true,
			error: null,
			runs: current?.runs ?? null
		};
		try {
			const res = await listJobRuns({ path: { job_key: jobKey }, query: { limit: HISTORY_LIMIT } });
			if (res.error || !res.data) {
				history[jobKey] = {
					...history[jobKey],
					loading: false,
					error: networkAwareError(res).title
				};
			} else {
				history[jobKey] = { ...history[jobKey], loading: false, runs: res.data };
			}
		} catch {
			history[jobKey] = {
				...history[jobKey],
				loading: false,
				error: 'Could not load recent runs.'
			};
		}
	}

	async function loadJobs(initial = false) {
		if (initial) {
			loading = true;
			error = null;
		}
		try {
			const res = await listJobs();
			if (res.error || !res.data) {
				// Stale content stays visible; the alert appears above it.
				error = networkAwareError(res).title;
			} else {
				const previous = jobs;
				jobs = res.data;
				error = null;
				for (const job of res.data) {
					const before = previous.find((j) => j.job_key === job.job_key)?.active_run;
					const wasActive = before && isActive(before.status);
					if (wasActive && before.id !== activeRun(job)?.id) {
						announcement = `${job.title} has finished.`;
						if (history[job.job_key]?.open) void loadHistory(job.job_key);
					}
				}
			}
		} catch {
			error = 'Could not load scheduled tasks.';
		}
		loading = false;
	}

	$effect(() => {
		if (canRead) {
			void untrack(() => loadJobs(true));
		} else {
			loading = false;
		}
	});

	$effect(() => {
		if (!canRead) return;
		const id = setInterval(
			() => {
				if (document.hidden) return;
				void loadJobs();
			},
			anyActive ? POLL_BUSY_MS : POLL_IDLE_MS
		);
		return () => clearInterval(id);
	});

	function handleToggle(jobKey: string, open: boolean) {
		const current = history[jobKey];
		history[jobKey] = current
			? { ...current, open }
			: { open, loading: false, error: null, runs: null };
		if (open && !current?.runs && !current?.loading) void loadHistory(jobKey);
	}

	async function handleRun(job: JobResponse) {
		if (starting !== null) return;
		starting = job.job_key;
		try {
			const res = await runJobNow({ path: { job_key: job.job_key } });
			if (res.error || !res.data) {
				toast.error(errorMessage(res.error));
			} else {
				const run = res.data;
				if (job.active_run?.id === run.id) {
					toast.info('Already in progress.');
				} else {
					toast.success("Started. It will run as soon as it's this task's turn.");
					announcement = `${job.title} has been started.`;
				}
				jobs = jobs.map((j) => (j.job_key === job.job_key ? { ...j, active_run: run } : j));
				if (history[job.job_key]?.open) void loadHistory(job.job_key);
			}
		} catch {
			toast.error('Could not start this task.');
		} finally {
			starting = null;
		}
	}
</script>

<svelte:head>
	<title>Scheduled tasks - Administration - Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-3xl flex-col gap-8">
		<BackButton fallback={resolve('/admin')} />
		<div>
			<h1 class="font-heading text-3xl font-semibold tracking-tight">Scheduled tasks</h1>
			<p class="mt-1 text-muted-foreground">
				Background jobs that keep this Menagerist tidy and backed up.
			</p>
		</div>

		<div class="sr-only" aria-live="polite" aria-atomic="true">{announcement}</div>

		{#if !canRead}
			<Alert.Root>
				<Alert.Description>Only administrators can access this area.</Alert.Description>
			</Alert.Root>
		{:else}
			{#if error}
				<Alert.Root variant="destructive">
					<Alert.Description>{error}</Alert.Description>
				</Alert.Root>
				<Button variant="outline" class="h-11 w-full sm:w-auto" onclick={() => void loadJobs(true)}>
					Retry
				</Button>
			{/if}

			{#if loading && jobs.length === 0}
				{#if loadingDisplay.show}
					<div class="space-y-4" aria-hidden="true">
						<Skeleton class="h-32 w-full rounded-xl" />
						<Skeleton class="h-32 w-full rounded-xl" />
						<Skeleton class="h-32 w-full rounded-xl" />
					</div>
				{/if}
			{:else if jobs.length === 0}
				{#if !error}
					<p class="text-sm text-muted-foreground">
						Nothing is set up to run in the background yet.
					</p>
				{/if}
			{:else}
				<ul class="space-y-4" aria-label="Scheduled tasks">
					{#each jobs as job (job.job_key)}
						{@const name = job.title}
						{@const description = job.description}
						{@const active = activeRun(job)}
						{@const hist = history[job.job_key]}
						<li>
							<Card.Root>
								<Card.Content class="flex flex-col gap-4 p-5">
									<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
										<div class="space-y-1">
											<div class="flex flex-wrap items-center gap-2">
												<h2 class="font-heading text-lg font-semibold">{name}</h2>
												{#if job.active_run}
													<Badge variant={badgeVariant(job.active_run.status)}>
														{runStatusLabel(job.active_run.status)}
													</Badge>
												{/if}
											</div>
											{#if description}
												<p class="text-sm text-muted-foreground">{description}</p>
											{/if}
											<p class="text-sm text-muted-foreground">
												{nextRunLabel(job, formatWhen)}
											</p>
										</div>

										{#if job.run_now_allowed && canRun}
											<Button
												type="button"
												variant="outline"
												class="h-11 shrink-0 sm:h-9"
												aria-label={`Run ${name} now`}
												disabled={starting === job.job_key || active !== null}
												onclick={() => handleRun(job)}
											>
												{#if starting === job.job_key || active?.status === 'running'}
													<Spinner class="size-4" />
												{/if}
												{#if active}
													{active.status === 'running' ? 'Running' : 'Waiting'}
												{:else}
													Run now
												{/if}
											</Button>
										{/if}
									</div>

									<Collapsible.Root
										open={hist?.open ?? false}
										onOpenChange={(open) => handleToggle(job.job_key, open)}
									>
										<Collapsible.Trigger
											class="group flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
										>
											Recent runs
											<ChevronDown
												class="size-4 transition-transform group-data-[state=open]:rotate-180"
											/>
										</Collapsible.Trigger>
										<Collapsible.Content class="pt-3">
											{#if hist?.error}
												<Alert.Root variant="destructive">
													<Alert.Description>{hist.error}</Alert.Description>
												</Alert.Root>
												<Button
													variant="outline"
													class="mt-2 h-9"
													onclick={() => void loadHistory(job.job_key)}
												>
													Retry
												</Button>
											{:else if hist?.loading && !hist.runs}
												<div class="space-y-2" aria-hidden="true">
													<Skeleton class="h-10 w-full rounded-lg" />
													<Skeleton class="h-10 w-full rounded-lg" />
												</div>
											{:else if hist?.runs && hist.runs.length === 0}
												<p class="text-sm text-muted-foreground">
													No runs yet. Start it above or wait for its next scheduled time.
												</p>
											{:else if hist?.runs}
												<ul
													class="divide-y rounded-lg border"
													aria-label={`Recent runs of ${name}`}
												>
													{#each hist.runs as run (run.id)}
														{@const duration = runDuration(run)}
														<li class="flex flex-col gap-1 px-3 py-2 text-sm">
															<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
																<Badge variant={badgeVariant(run.status)}>
																	{runStatusLabel(run.status)}
																</Badge>
																<span>{formatWhen(run.started_at ?? run.scheduled_for)}</span>
																{#if duration}
																	<span class="text-muted-foreground">{duration}</span>
																{/if}
																<span class="text-muted-foreground">
																	{startedByHand(run)
																		? 'Started by an administrator'
																		: 'On schedule'}
																</span>
															</div>
															{#if run.error && (run.status === 'failed' || run.status === 'abandoned')}
																<details class="text-xs text-muted-foreground">
																	<summary class="cursor-pointer">Details</summary>
																	<p class="mt-1 break-words whitespace-pre-wrap">{run.error}</p>
																</details>
															{/if}
														</li>
													{/each}
												</ul>
											{/if}
										</Collapsible.Content>
									</Collapsible.Root>
								</Card.Content>
							</Card.Root>
						</li>
					{/each}
				</ul>
			{/if}
		{/if}
	</div>
</main>
