<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { tick, untrack } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { Info, Pencil, RefreshCw, RotateCcw, Server } from '@lucide/svelte';
	import { getMySettingsSchema, type SettingResponse } from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import { auth } from '$lib/auth.svelte.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import { formatDateTime } from '$lib/format-date';
	import { withAutomaticExample } from '$lib/automatic-labels';
	import { coreForProp } from '$lib/field-types';
	import { offlineController } from '$lib/offline.svelte';
	import { OFFLINE_PREFERENCES, preferences } from '$lib/preferences.svelte';
	import {
		formProp,
		groupOfSetting,
		groupSettings,
		pickSection,
		schemaProperties,
		settingId,
		settingKeyFromHash,
		sourceLabel
	} from '$lib/settings-form';
	import SettingsSectionNav, { type Section } from '$lib/components/settings-section-nav.svelte';
	import { desktop } from '$lib/viewport.svelte';
	import BackButton from '$lib/components/back-button.svelte';
	import IconButton from '$lib/components/icon-button.svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';

	let schema = $state.raw<unknown>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let saving = $state<string | null>(null);

	const props = $derived(schemaProperties(schema));
	// Hidden settings are changed elsewhere in the app; only what the schema offers shows here.
	const shown = $derived(preferences.items.filter((item) => !item.hidden && item.key in props));
	const offline = $derived(offlineController.offline);
	// Sections as on the admin settings page: one at a time, named by `?section=`; a link to
	// `#setting-<key>` opens the section holding that preference and highlights it.
	const groups = $derived(groupSettings(shown));
	const linkedKey = $derived(settingKeyFromHash(page.url.hash));
	const activeKey = $derived(
		pickSection(groups, page.url.searchParams.get('section'), groupOfSetting(shown, linkedKey))
	);
	const activeGroup = $derived(groups.find((g) => g.group === activeKey));
	const sections = $derived<Section[]>(
		groups.map((g) => ({
			key: g.group,
			label: g.label,
			count: g.items.length,
			href: `${resolve('/settings/preferences')}?section=${encodeURIComponent(g.group)}`
		}))
	);
	let highlighted = $state<string | null>(null);
	// Re-read when a preference changes, so the line shows the choices just made.
	const preview = $derived.by(() => {
		void preferences.items;
		return formatDateTime(new Date().toISOString()).local;
	});
	const loadingDisplay = delayedLoading();
	$effect(() => loadingDisplay.set(loading));
	$effect(() => {
		const owner = auth.user?.id;
		void offlineController.retryCount;
		if (owner) untrack(() => void load(owner));
	});

	async function load(owner: string) {
		loading = schema === null;
		error = null;
		try {
			const [result] = await Promise.all([getMySettingsSchema(), preferences.load(owner)]);
			if (result.error || !result.data) error = networkAwareError(result).title;
			else schema = result.data;
		} catch {
			error = networkAwareError({}).title;
		} finally {
			loading = false;
		}
	}

	function openSection(section: Section) {
		void goto(section.href, { noScroll: true, keepFocus: true });
	}

	// Brings a linked preference into view and marks it for a moment once the page has loaded.
	$effect(() => {
		const key = linkedKey;
		if (loading || key === null || !shown.some((item) => item.key === key)) return;
		let timer: ReturnType<typeof setTimeout>;
		void tick().then(() => {
			const heading = document.getElementById(settingId(key));
			if (!heading) return;
			heading.scrollIntoView({ block: 'center' });
			heading.focus({ preventScroll: true });
			highlighted = key;
			timer = setTimeout(() => (highlighted = null), 2500);
		});
		return () => clearTimeout(timer);
	});

	function widgetFor(item: SettingResponse) {
		const prop = withAutomaticExample(item.key, formProp(props[item.key]));
		const core = coreForProp(prop);
		return core ? { prop, core } : null;
	}

	async function change(item: SettingResponse, value: unknown) {
		if (saving || value === item.value) return;
		saving = item.key;
		// Clearing a choice means "no preference": go back to the default.
		const outcome =
			value === '' || value === null
				? await preferences.reset(item.key)
				: await preferences.save(item.key, value as SettingResponse['value']);
		saving = null;
		if (!outcome.ok) toast.error(outcome.message);
		else toast.success('Saved');
	}

	async function reset(item: SettingResponse) {
		if (saving) return;
		saving = item.key;
		const outcome = await preferences.reset(item.key);
		saving = null;
		if (!outcome.ok) toast.error(outcome.message);
		else toast('Back to the default');
	}
</script>

<svelte:head><title>Preferences - Menagerist</title></svelte:head>

<Page width="reading">
	<BackButton peer fallback={resolve('/settings')} />
	<div>
		<h1 class="font-heading text-3xl font-semibold tracking-tight">Preferences</h1>
		<p class="mt-1 text-muted-foreground">
			Choose how Menagerist works for you. Your choices follow you to every device.
		</p>
	</div>

	{#if offline}
		<Alert.Root>
			<Alert.Description>{OFFLINE_PREFERENCES}</Alert.Description>
		</Alert.Root>
	{/if}

	{#if error && shown.length === 0}
		<Alert.Root variant="destructive">
			<Alert.Description>{error}</Alert.Description>
			<Button
				variant="outline"
				class="mt-2 pointer-coarse:h-11"
				disabled={loading}
				onclick={() => auth.user && load(auth.user.id)}
			>
				<RefreshCw class="size-4" aria-hidden="true" />Retry
			</Button>
		</Alert.Root>
	{/if}

	{#if loadingDisplay.show}
		<div role="status" aria-label="Loading preferences" class="space-y-3">
			<Skeleton class="h-24 w-full" />
		</div>
	{:else if activeGroup}
		<div
			class={groups.length > 1
				? 'grid gap-4 lg:grid-cols-[12rem_minmax(0,1fr)] lg:gap-8'
				: 'flex flex-col gap-2'}
		>
			{#if groups.length > 1}
				<div class="lg:sticky lg:top-4 lg:self-start">
					<SettingsSectionNav
						{sections}
						active={activeKey}
						variant={desktop.current ? 'list' : 'select'}
						onselect={openSection}
					/>
				</div>
			{/if}
			<section class="flex min-w-0 flex-col gap-2" aria-labelledby="preferences-section-heading">
				<h2 id="preferences-section-heading" class="font-heading text-lg font-semibold">
					{activeGroup.label}
				</h2>
				<ul class="divide-y rounded-xl border bg-card">
					{#each activeGroup.items as item (item.key)}
						{@const widget = widgetFor(item)}
						{@const busy = saving === item.key}
						<li
							class="grid gap-x-8 gap-y-2 px-4 py-3 transition-colors duration-700 motion-reduce:transition-none lg:grid-cols-[minmax(0,1fr)_minmax(0,18rem)] {highlighted ===
							item.key
								? 'bg-accent'
								: ''}"
						>
							<div class="space-y-1">
								<div class="flex flex-wrap items-center gap-2">
									<h3
										id={settingId(item.key)}
										tabindex="-1"
										class="font-heading font-semibold outline-none focus-visible:underline"
									>
										{item.title}
									</h3>
									<Badge variant="secondary">
										{#if item.source === 'env_default'}
											<Server aria-hidden="true" />
										{:else if item.source === 'default'}
											<Info aria-hidden="true" />
										{:else}
											<Pencil aria-hidden="true" />
										{/if}
										{sourceLabel(item)}
									</Badge>
								</div>
								{#if item.description}
									<p class="text-sm text-muted-foreground">{item.description}</p>
								{/if}
							</div>
							<div class="flex items-center gap-2">
								{#if widget}
									{@const Input = widget.core.InputWidget}
									<fieldset
										class="flex min-w-0 flex-1"
										class:opacity-60={busy}
										disabled={offline || busy}
									>
										<Input
											value={item.value}
											onChange={(value) => change(item, value)}
											ariaLabel={item.title}
											prop={widget.prop}
										/>
									</fieldset>
								{/if}
								{#if item.source === 'user'}
									<IconButton
										label="Reset {item.title} to the default"
										disabled={offline || busy}
										onclick={() => reset(item)}
									>
										<RotateCcw />
									</IconButton>
								{/if}
							</div>
						</li>
					{/each}
				</ul>
				{#if activeGroup.group === 'datetime'}
					<p class="text-sm text-muted-foreground" aria-live="polite">
						Dates and times read like this: <span class="text-foreground">{preview}</span>
					</p>
				{/if}
			</section>
		</div>
	{:else if !loading && !error}
		<p class="rounded-xl border p-6 text-muted-foreground">There is nothing to choose yet.</p>
	{/if}
</Page>
