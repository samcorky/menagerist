<script lang="ts">
	import { untrack } from 'svelte';
	import { resolve } from '$app/paths';
	import { toast } from 'svelte-sonner';
	import { Check, ChevronDown, RotateCcw } from '@lucide/svelte';
	import {
		getSettingsSchema,
		listInstanceSettings,
		listJobRuns,
		listJobs,
		resetInstanceSetting,
		runJobNow,
		updateInstanceSettings,
		type JobResponse,
		type JobRunResponse,
		type SettingResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { auth } from '$lib/auth.svelte.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import { wide } from '$lib/viewport.svelte';
	import { coreForProp } from '$lib/field-types';
	import { explainCron } from '$lib/field-types/cron/explain';
	import { formatDateTime } from '$lib/format-date';
	import {
		isActive,
		lastRunLabel,
		nextRunLabel,
		runDuration,
		runStatusLabel,
		runTone,
		scheduleLabel,
		startedByHand,
		type RunStatus
	} from '$lib/scheduled-tasks';
	import {
		coerce,
		formProp,
		isChanged,
		lockedNote,
		schemaProperties,
		updateBody,
		type SettingValue
	} from '$lib/settings-form';
	import BackButton from '$lib/components/back-button.svelte';
	import DataTable from '$lib/components/data-table.svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge, type BadgeVariant } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';
	import * as Table from '$lib/components/ui/table/index.js';

	type Panel = 'runs';

	type History = {
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
	let confirming = $state<JobResponse | null>(null);
	let editing = $state<JobResponse | null>(null);
	let panels = $state<Record<string, Panel | undefined>>({});
	let history = $state<Record<string, History>>({});
	let announcement = $state('');

	// Schedules live in the settings, so a task's schedule is edited through them.
	let settings = $state.raw<SettingResponse[]>([]);
	let settingsSchema = $state.raw<unknown>(null);
	let drafts = $state<Record<string, unknown>>({});
	let draftErrors = $state<Record<string, string>>({});
	let saving = $state<string | null>(null);

	const loadingDisplay = delayedLoading();
	$effect(() => {
		loadingDisplay.set(loading);
	});

	const canRead = $derived(auth.can('scheduling:job:read'));
	const canRun = $derived(auth.can('scheduling:job:run'));
	const canEditSchedules = $derived(
		auth.can('settings:instance:read') && auth.can('settings:instance:write')
	);
	const anyActive = $derived(jobs.some((j) => j.active_run && isActive(j.active_run.status)));
	const properties = $derived(schemaProperties(settingsSchema));

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

	function scheduleSetting(job: JobResponse): SettingResponse | undefined {
		return job.schedule_key ? settings.find((s) => s.key === job.schedule_key) : undefined;
	}

	function scheduleWidget(setting: SettingResponse) {
		const schemaProperty = properties[setting.key];
		if (schemaProperty === undefined) return null;
		const prop = formProp(schemaProperty);
		const core = coreForProp(prop);
		return core ? { prop, core } : null;
	}

	function canEditSchedule(job: JobResponse): boolean {
		const setting = scheduleSetting(job);
		return (
			canEditSchedules &&
			setting !== undefined &&
			!setting.locked &&
			scheduleWidget(setting) !== null
		);
	}

	function draftChanged(setting: SettingResponse): boolean {
		const widget = scheduleWidget(setting);
		return (
			widget !== null && isChanged(widget.prop, setting.value as SettingValue, drafts[setting.key])
		);
	}

	function explain(expression: string | null): string | null {
		if (!expression) return null;
		const reading = explainCron(expression);
		return reading.ok ? reading.text : null;
	}

	async function loadHistory(jobKey: string) {
		const current = history[jobKey];
		history[jobKey] = { loading: true, error: null, runs: current?.runs ?? null };
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
						if (panels[job.job_key] === 'runs') void loadHistory(job.job_key);
					}
				}
			}
		} catch {
			error = 'Could not load scheduled tasks.';
		}
		loading = false;
	}

	// Without the settings the table still works; only changing a schedule is unavailable.
	async function loadSettings() {
		if (!auth.can('settings:instance:read')) return;
		try {
			const [schemaResult, listResult] = await Promise.all([
				getSettingsSchema(),
				listInstanceSettings()
			]);
			if (schemaResult.data && listResult.data) {
				settingsSchema = schemaResult.data;
				applySettings(listResult.data);
			}
		} catch {
			// Schedules stay read-only.
		}
	}

	function applySettings(updated: SettingResponse[]) {
		settings = updated;
		for (const setting of updated) {
			if (panels[setting.key] === undefined) drafts[setting.key] = setting.value;
		}
	}

	$effect(() => {
		if (canRead) {
			void untrack(() => loadJobs(true));
			void untrack(() => loadSettings());
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

	function toggle(job: JobResponse, panel: Panel) {
		const key = job.job_key;
		if (panels[key] === panel) {
			panels[key] = undefined;
			return;
		}
		panels[key] = panel;
		if (panel === 'runs' && !history[key]?.runs && !history[key]?.loading) {
			void loadHistory(key);
		}
	}

	function openSchedule(job: JobResponse) {
		const setting = scheduleSetting(job);
		if (setting) {
			drafts[setting.key] = setting.value;
			delete draftErrors[setting.key];
		}
		editing = job;
	}

	// A heavy or disruptive task asks first; the rest start straight away.
	function requestRun(job: JobResponse) {
		if (job.confirm_required) confirming = job;
		else void handleRun(job);
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
				if (panels[job.job_key] === 'runs') void loadHistory(job.job_key);
			}
		} catch {
			toast.error('Could not start this task.');
		} finally {
			starting = null;
		}
	}

	type Outcome = { ok: true } | { ok: false };

	// Shows its own failure (the field message for a rejected value, otherwise a toast).
	async function send(
		setting: SettingResponse,
		call: () => Promise<{
			data?: SettingResponse | SettingResponse[];
			error?: unknown;
			response?: Response | null;
		}>
	): Promise<Outcome> {
		saving = setting.key;
		try {
			const result = await call();
			const updated = Array.isArray(result.data) ? result.data : result.data && [result.data];
			if (!result.error && updated) {
				settings = settings.map((s) => updated.find((u) => u.key === s.key) ?? s);
				for (const item of updated) {
					drafts[item.key] = item.value;
					delete draftErrors[item.key];
				}
				// The next run follows the new schedule.
				await loadJobs();
				return { ok: true };
			}
			const status = result.response?.status;
			if (status === 400) {
				draftErrors[setting.key] = errorMessage(result.error);
			} else if (status === 409) {
				toast.error('This schedule is now set by your deployment.');
				await loadSettings();
			} else {
				const failure = networkAwareError(result);
				toast.error(failure.title, { description: failure.description });
			}
		} catch {
			toast.error('Could not save. Check your connection and try again.');
		} finally {
			saving = null;
		}
		return { ok: false };
	}

	async function saveSchedule(job: JobResponse) {
		const setting = scheduleSetting(job);
		const widget = setting && scheduleWidget(setting);
		if (!setting || !widget || saving) return;
		const coerced = coerce(widget.prop, drafts[setting.key]);
		if (!coerced.ok) {
			draftErrors[setting.key] = coerced.message;
			return;
		}
		delete draftErrors[setting.key];
		const outcome = await send(setting, () =>
			updateInstanceSettings({ body: updateBody(setting.key, coerced.value) })
		);
		if (outcome.ok) {
			toast.success('Schedule saved');
			editing = null;
		}
	}

	async function resetSchedule(job: JobResponse) {
		const setting = scheduleSetting(job);
		if (!setting || saving) return;
		const outcome = await send(setting, () => resetInstanceSetting({ path: { key: setting.key } }));
		if (outcome.ok) {
			toast('Schedule reset to its default');
			editing = null;
		}
	}
</script>

{#snippet actions(job: JobResponse, inTable: boolean)}
	{@const active = activeRun(job)}
	{@const size = inTable ? 'h-9 w-full px-3' : 'h-11 flex-1'}
	<div
		class={inTable ? 'grid grid-cols-[6.5rem_9rem_9rem] justify-end gap-1' : 'flex flex-wrap gap-2'}
	>
		{#if job.run_now_allowed && canRun}
			<Button
				type="button"
				variant="outline"
				class={size}
				aria-label={`Run ${job.title} now`}
				disabled={starting === job.job_key || active !== null}
				onclick={() => requestRun(job)}
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
		{:else if inTable}
			<span aria-hidden="true"></span>
		{/if}
		{#if canEditSchedule(job)}
			<Button
				type="button"
				variant="outline"
				class={size}
				aria-label={`Change schedule of ${job.title}`}
				onclick={() => openSchedule(job)}
			>
				Change schedule
			</Button>
		{:else if inTable}
			<span aria-hidden="true"></span>
		{/if}
		<Button
			type="button"
			variant="outline"
			class={size}
			aria-expanded={panels[job.job_key] === 'runs'}
			aria-label={`Recent runs of ${job.title}`}
			onclick={() => toggle(job, 'runs')}
		>
			Recent runs
			<ChevronDown
				class={'size-4 transition-transform ' +
					(panels[job.job_key] === 'runs' ? 'rotate-180' : '')}
			/>
		</Button>
	</div>
{/snippet}

{#snippet lastRun(job: JobResponse)}
	{#if job.last_run}
		<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
			<Badge variant={badgeVariant(job.last_run.status)}>
				{runStatusLabel(job.last_run.status)}
			</Badge>
			<span class="text-muted-foreground">{lastRunLabel(job.last_run, formatWhen)}</span>
		</div>
	{:else}
		<span class="text-muted-foreground">Never run</span>
	{/if}
{/snippet}

{#snippet scheduleEditor(job: JobResponse)}
	{@const setting = scheduleSetting(job)}
	{@const widget = setting ? scheduleWidget(setting) : null}
	{#if setting && widget}
		{@const Input = widget.core.InputWidget}
		{@const isSaving = saving === setting.key}
		<div class="space-y-3">
			<div class:opacity-60={isSaving}>
				<Input
					value={drafts[setting.key]}
					onChange={(value) => {
						drafts[setting.key] = value;
						delete draftErrors[setting.key];
					}}
					ariaLabel={`Schedule for ${job.title}`}
					prop={widget.prop}
				/>
			</div>
			{#if draftErrors[setting.key]}
				<p role="alert" class="text-sm text-destructive">{draftErrors[setting.key]}</p>
			{/if}
			<div class="flex flex-wrap gap-2">
				<Button
					class="h-11"
					disabled={isSaving || !draftChanged(setting)}
					onclick={() => saveSchedule(job)}
				>
					{#if isSaving}<Spinner
							class="motion-reduce:animate-none"
							aria-hidden="true"
						/>{:else}<Check class="size-4" aria-hidden="true" />{/if}
					{isSaving ? 'Saving...' : 'Save schedule'}
				</Button>
				{#if setting.source === 'instance'}
					<Button
						variant="ghost"
						class="h-11"
						disabled={isSaving}
						onclick={() => resetSchedule(job)}
					>
						<RotateCcw class="size-4" aria-hidden="true" />Reset to default
					</Button>
				{/if}
				<Button variant="ghost" class="h-11" disabled={isSaving} onclick={() => (editing = null)}>
					Cancel
				</Button>
			</div>
		</div>
	{/if}
{/snippet}

{#snippet detail(job: JobResponse)}
	{@const panel = panels[job.job_key]}
	{#if panel === 'runs'}
		{@const hist = history[job.job_key]}
		{#if hist?.error}
			<Alert.Root variant="destructive">
				<Alert.Description>{hist.error}</Alert.Description>
			</Alert.Root>
			<Button variant="outline" class="mt-2 h-9" onclick={() => void loadHistory(job.job_key)}>
				Retry
			</Button>
		{:else if !hist || (hist.loading && !hist.runs)}
			<div class="space-y-2" aria-hidden="true">
				<Skeleton class="h-10 w-full rounded-lg" />
				<Skeleton class="h-10 w-full rounded-lg" />
			</div>
		{:else if hist.runs && hist.runs.length === 0}
			<p class="text-sm text-muted-foreground">
				No runs yet. Start it above or wait for its next scheduled time.
			</p>
		{:else if hist.runs}
			<ul class="divide-y rounded-lg border bg-card" aria-label={`Recent runs of ${job.title}`}>
				{#each hist.runs as run (run.id)}
					{@const duration = runDuration(run)}
					<li class="flex flex-col gap-1 px-3 py-2 text-sm">
						<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
							<Badge variant={badgeVariant(run.status)}>{runStatusLabel(run.status)}</Badge>
							<span>{formatWhen(run.started_at ?? run.scheduled_for)}</span>
							{#if duration}
								<span class="text-muted-foreground">{duration}</span>
							{/if}
							<span class="text-muted-foreground">
								{startedByHand(run) ? 'Started by an administrator' : 'On schedule'}
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
	{/if}
{/snippet}

<ResponsiveDialog.Root
	open={confirming !== null}
	onOpenChange={(open) => {
		if (!open) confirming = null;
	}}
>
	<ResponsiveDialog.Content title={`Run "${confirming?.title ?? ''}" now?`} size="sm">
		<ResponsiveDialog.Description>
			{confirming?.description}
			Only start it when you need to.
		</ResponsiveDialog.Description>
		<div class="mt-4 flex justify-end gap-2">
			<Button variant="outline" class="h-11" onclick={() => (confirming = null)}>Cancel</Button>
			<Button
				class="h-11"
				onclick={() => {
					const job = confirming;
					confirming = null;
					if (job) void handleRun(job);
				}}
			>
				Run now
			</Button>
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>

<ResponsiveDialog.Root
	open={editing !== null}
	onOpenChange={(open) => {
		if (!open && saving === null) editing = null;
	}}
>
	<ResponsiveDialog.Content title="Change schedule" size="sm">
		{#if editing}
			<ResponsiveDialog.Description>
				When "{editing.title}" runs by itself. It is read in this Menagerist's own timezone.
			</ResponsiveDialog.Description>
			<div class="mt-4">{@render scheduleEditor(editing)}</div>
		{/if}
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>

<svelte:head>
	<title>Scheduled tasks - Administration - Menagerist</title>
</svelte:head>

<main class="flex-1 px-4 py-8 sm:px-6">
	<div class="mx-auto flex max-w-5xl flex-col gap-8">
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
					<div class="space-y-3" aria-hidden="true">
						<Skeleton class="h-16 w-full rounded-xl" />
						<Skeleton class="h-16 w-full rounded-xl" />
						<Skeleton class="h-16 w-full rounded-xl" />
					</div>
				{/if}
			{:else if jobs.length === 0}
				{#if !error}
					<p class="text-sm text-muted-foreground">
						Nothing is set up to run in the background yet.
					</p>
				{/if}
			{:else}
				{#if wide.current}
					<DataTable
						label="Scheduled tasks"
						columns={[
							{ label: 'Task' },
							{ label: 'Schedule' },
							{ label: 'Next run' },
							{ label: 'Last run' },
							{ label: 'Actions', end: true }
						]}
					>
						{#each jobs as job (job.job_key)}
							{@const setting = scheduleSetting(job)}
							<Table.Row>
								<Table.Head
									scope="row"
									class="h-auto max-w-xs px-4 py-3 align-top whitespace-normal"
								>
									<div class="font-medium">{job.title}</div>
									{#if job.description}
										<div class="mt-0.5 text-xs font-normal text-muted-foreground">
											{job.description}
										</div>
									{/if}
								</Table.Head>
								<Table.Cell>
									<div>{scheduleLabel(job, explain)}</div>
									{#if setting?.locked}
										<div class="mt-0.5 text-xs text-muted-foreground">{lockedNote(setting)}</div>
									{/if}
								</Table.Cell>
								<Table.Cell class="text-muted-foreground"
									>{nextRunLabel(job, formatWhen)}</Table.Cell
								>
								<Table.Cell>{@render lastRun(job)}</Table.Cell>
								<Table.Cell>{@render actions(job, true)}</Table.Cell>
							</Table.Row>
							{#if panels[job.job_key]}
								<Table.Row class="bg-muted/20 hover:bg-muted/20">
									<Table.Cell colspan={5} class="py-4">{@render detail(job)}</Table.Cell>
								</Table.Row>
							{/if}
						{/each}
					</DataTable>
				{:else}
					<ul class="space-y-3" aria-label="Scheduled tasks">
						{#each jobs as job (job.job_key)}
							{@const setting = scheduleSetting(job)}
							<li>
								<Card.Root>
									<Card.Content class="flex flex-col gap-3 p-4">
										<div class="space-y-0.5">
											<h2 class="font-medium">{job.title}</h2>
											{#if job.description}
												<p class="text-xs text-muted-foreground">{job.description}</p>
											{/if}
										</div>
										<dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
											<dt class="text-muted-foreground">Schedule</dt>
											<dd>{scheduleLabel(job, explain)}</dd>
											<dt class="text-muted-foreground">Next run</dt>
											<dd>{nextRunLabel(job, formatWhen)}</dd>
											<dt class="text-muted-foreground">Last run</dt>
											<dd>{@render lastRun(job)}</dd>
										</dl>
										{#if setting?.locked}
											<p class="text-xs text-muted-foreground">{lockedNote(setting)}</p>
										{/if}
										{@render actions(job, false)}
										{#if panels[job.job_key]}
											<div class="border-t pt-3">{@render detail(job)}</div>
										{/if}
									</Card.Content>
								</Card.Root>
							</li>
						{/each}
					</ul>
				{/if}
			{/if}
		{/if}
	</div>
</main>
