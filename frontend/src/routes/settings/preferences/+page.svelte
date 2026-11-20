<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import { resolve } from '$app/paths';
	import { untrack } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { Info, Pencil, RefreshCw, RotateCcw, Server } from '@lucide/svelte';
	import { getMySettingsSchema, type SettingResponse } from '$lib/api/client';
	import { networkAwareError } from '$lib/api/errors';
	import { auth } from '$lib/auth.svelte.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import { formatDateTime } from '$lib/format-date';
	import { coreForProp } from '$lib/field-types';
	import { offlineController } from '$lib/offline.svelte';
	import { OFFLINE_PREFERENCES, preferences } from '$lib/preferences.svelte';
	import { formProp, schemaProperties, settingId, sourceLabel } from '$lib/settings-form';
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

	function widgetFor(item: SettingResponse) {
		const prop = formProp(props[item.key]);
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
	{:else if shown.length > 0}
		<ul class="divide-y rounded-xl border bg-card">
			{#each shown as item (item.key)}
				{@const widget = widgetFor(item)}
				{@const busy = saving === item.key}
				<li class="grid gap-x-8 gap-y-2 px-4 py-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,18rem)]">
					<div class="space-y-1">
						<div class="flex flex-wrap items-center gap-2">
							<h2 id={settingId(item.key)} class="font-heading font-semibold">{item.title}</h2>
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
		<p class="text-sm text-muted-foreground" aria-live="polite">
			Dates and times read like this: <span class="text-foreground">{preview}</span>
		</p>
	{:else if !loading && !error}
		<p class="rounded-xl border p-6 text-muted-foreground">There is nothing to choose yet.</p>
	{/if}
</Page>
