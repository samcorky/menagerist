<script lang="ts">
	import Page from '$lib/components/page.svelte';
	import { resolve } from '$app/paths';
	import { tick, untrack } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { Check, Pencil, Info, Server, RefreshCw, RotateCcw, X } from '@lucide/svelte';
	import {
		getSettingsSchema,
		listInstanceSettings,
		updateInstanceSettings,
		resetInstanceSetting,
		type SettingResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { auth } from '$lib/auth.svelte.js';
	import { delayedLoading } from '$lib/delayed-loading.svelte.js';
	import { coreForProp } from '$lib/field-types';
	import {
		coerce,
		formProp,
		groupSettings,
		isChanged,
		lockedNote,
		restartNote,
		schemaProperties,
		sourceLabel,
		staleNote,
		updateBody,
		type SettingValue
	} from '$lib/settings-form';
	import BackButton from '$lib/components/back-button.svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import CollapsibleSection from '$lib/components/collapsible-section.svelte';
	import IconButton from '$lib/components/icon-button.svelte';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	const canRead = $derived(auth.can('settings:instance:read'));
	const canWrite = $derived(auth.can('settings:instance:write'));

	let items = $state.raw<SettingResponse[]>([]);
	let schema = $state.raw<unknown>(null);
	let drafts = $state<Record<string, unknown>>({});
	let fieldErrors = $state<Record<string, string>>({});
	let loading = $state(true);
	let error = $state<string | null>(null);
	let saving = $state<string | null>(null);

	const groups = $derived(groupSettings(items));
	const props = $derived(schemaProperties(schema));
	const loadingDisplay = delayedLoading();
	$effect(() => loadingDisplay.set(loading));
	$effect(() => {
		if (canRead) untrack(() => void load());
		else loading = false;
	});

	function headingId(key: string) {
		return `setting-${key}`;
	}
	async function focusHeading(key: string) {
		await tick();
		document.getElementById(headingId(key))?.focus();
	}
	function widgetFor(item: SettingResponse) {
		const schemaProperty = props[item.key];
		if (schemaProperty === undefined) return null;
		const prop = formProp(schemaProperty);
		const core = coreForProp(prop);
		return core ? { prop, core } : null;
	}
	function changed(item: SettingResponse) {
		const widget = widgetFor(item);
		return widget !== null && isChanged(widget.prop, item.value as SettingValue, drafts[item.key]);
	}
	function plainText(value: unknown) {
		return Array.isArray(value) ? value.join(', ') : String(value ?? '');
	}
	function setDraft(key: string, value: unknown) {
		drafts[key] = value;
		delete fieldErrors[key];
	}
	function replaceItems(updated: SettingResponse[]) {
		items = items.map((item) => updated.find((u) => u.key === item.key) ?? item);
		for (const item of updated) {
			drafts[item.key] = item.value;
			delete fieldErrors[item.key];
		}
	}

	async function load(quiet = false) {
		if (!quiet) loading = true;
		error = null;
		try {
			const [schemaResult, listResult] = await Promise.all([
				getSettingsSchema(),
				listInstanceSettings()
			]);
			if (schemaResult.error || !listResult.data) {
				error = networkAwareError(listResult.error ? listResult : schemaResult).title;
			} else {
				schema = schemaResult.data;
				// A quiet reload keeps edits the person made, unless the setting is now locked.
				const kept = quiet ? new Set(items.filter(changed).map((item) => item.key)) : new Set();
				items = listResult.data;
				drafts = Object.fromEntries(
					items.map((item) => [
						item.key,
						kept.has(item.key) && !item.locked ? drafts[item.key] : item.value
					])
				);
				fieldErrors = {};
			}
		} catch {
			error = 'Could not load settings. Check your connection and try again.';
		} finally {
			loading = false;
		}
	}

	type Outcome = { ok: true; item: SettingResponse } | { ok: false };

	// Shows its own failure (a toast, or the field message for a rejected value) and reports back.
	async function send(
		key: string,
		call: () => Promise<{
			data?: SettingResponse | SettingResponse[];
			error?: unknown;
			response?: Response | null;
		}>,
		showRejection: (message: string) => void
	): Promise<Outcome> {
		saving = key;
		try {
			const result = await call();
			const status = result.response?.status;
			const updated = Array.isArray(result.data) ? result.data : result.data && [result.data];
			const item = updated?.find((u) => u.key === key);
			if (!result.error && updated && item) {
				replaceItems(updated);
				return { ok: true, item };
			}
			if (status === 400) showRejection(errorMessage(result.error));
			else if (status === 409) {
				toast.error('This setting is now set by your deployment.');
				await load(true);
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

	// Puts a setting back to what it was before a change.
	async function restore(previous: SettingResponse) {
		const key = previous.key;
		const outcome = await send(
			key,
			() =>
				previous.source === 'default'
					? resetInstanceSetting({ path: { key } })
					: updateInstanceSettings({ body: updateBody(key, previous.value as SettingValue) }),
			(message) => toast.error(message)
		);
		if (outcome.ok) toast('Change undone');
		await focusHeading(key);
	}

	async function save(item: SettingResponse) {
		const widget = widgetFor(item);
		if (!widget || saving || !canWrite) return;
		const coerced = coerce(widget.prop, drafts[item.key]);
		if (!coerced.ok) {
			fieldErrors[item.key] = coerced.message;
			return;
		}
		delete fieldErrors[item.key];
		const outcome = await send(
			item.key,
			() => updateInstanceSettings({ body: updateBody(item.key, coerced.value) }),
			(message) => (fieldErrors[item.key] = message)
		);
		if (outcome.ok) {
			toast.success('Saved', {
				action: { label: 'Undo', onClick: () => void restore(item) },
				duration: 5000
			});
			await focusHeading(item.key);
		}
	}

	async function discard(item: SettingResponse) {
		drafts[item.key] = item.value;
		delete fieldErrors[item.key];
		await focusHeading(item.key);
	}

	async function reset(item: SettingResponse) {
		if (saving || !canWrite) return;
		const key = item.key;
		const outcome = await send(
			key,
			() => resetInstanceSetting({ path: { key } }),
			(message) => toast.error(message)
		);
		if (outcome.ok) {
			toast('Reset to default', {
				action: {
					label: 'Undo',
					onClick: () => void restore({ ...item, source: 'instance' })
				},
				duration: 5000
			});
			await focusHeading(key);
		}
	}
</script>

<svelte:head><title>Settings - Menagerist</title></svelte:head>

<Page width="reading">
	<BackButton fallback={resolve('/admin')} />
	<div>
		<h1 class="font-heading text-3xl font-semibold tracking-tight">Settings</h1>
		<p class="mt-1 text-muted-foreground">Change how this Menagerist runs.</p>
	</div>

	{#if !canRead}
		<Alert.Root>
			<Alert.Description>Only administrators can change settings.</Alert.Description>
		</Alert.Root>
	{:else}
		{#if error}
			<Alert.Root variant="destructive">
				<Alert.Description>{error}</Alert.Description>
				<Button
					variant="outline"
					class="mt-2 pointer-coarse:h-11"
					disabled={loading}
					onclick={() => load()}
				>
					<RefreshCw class="size-4" aria-hidden="true" />Retry
				</Button>
			</Alert.Root>
		{/if}
		{#if loadingDisplay.show}
			<div role="status" aria-label="Loading settings" class="space-y-3">
				<Skeleton class="h-40 w-full" /><Skeleton class="h-40 w-full" />
			</div>
		{:else if !loading && !error && items.length === 0}
			<p class="rounded-xl border p-6 text-muted-foreground">
				There are no settings to change yet.
			</p>
		{/if}

		{#each groups as group (group.group)}
			<CollapsibleSection
				id="admin-settings-{group.group}"
				title={group.label}
				count={group.items.length}
				class="gap-2"
			>
				<ul class="divide-y rounded-xl border bg-card" aria-busy={loading}>
					{#each group.items as item (item.key)}
						{@const widget = widgetFor(item)}
						{@const editable = canWrite && !item.locked && widget !== null}
						{@const isSaving = saving === item.key}
						{@const locked = lockedNote(item)}
						{@const restart = restartNote(item)}
						{@const stale = staleNote(item)}
						<li class="grid gap-x-8 gap-y-2 px-4 py-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
							<div class="space-y-1">
								<div class="flex flex-wrap items-center gap-2">
									<h3
										id={headingId(item.key)}
										tabindex="-1"
										class="font-heading font-semibold outline-none focus-visible:underline"
									>
										{item.title}
									</h3>
									<Badge variant="secondary">
										{#if item.source === 'env'}
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
								{#if locked}<p class="text-sm text-muted-foreground">{locked}</p>{/if}
								{#if restart}<p class="text-sm text-muted-foreground">{restart}</p>{/if}
								{#if stale}<p class="text-sm text-muted-foreground">{stale}</p>{/if}
							</div>

							<div class="space-y-2">
								{#if editable && widget}
									{@const Input = widget.core.InputWidget}
									<div class:opacity-60={isSaving}>
										<Input
											value={drafts[item.key]}
											onChange={(value) => setDraft(item.key, value)}
											ariaLabel={item.title}
											prop={widget.prop}
										/>
									</div>
								{:else if widget?.core.ViewWidget}
									{@const View = widget.core.ViewWidget}
									<View value={item.value} prop={widget.prop} />
								{:else}
									<p class="text-sm">{plainText(item.value)}</p>
								{/if}

								{#if fieldErrors[item.key]}
									<p role="alert" class="text-sm text-destructive">{fieldErrors[item.key]}</p>
								{/if}

								{#if editable && (changed(item) || item.source === 'instance')}
									<div class="flex flex-wrap items-center gap-2">
										{#if changed(item)}
											<Button
												class="pointer-coarse:h-11"
												disabled={isSaving}
												onclick={() => save(item)}
											>
												{#if isSaving}<Spinner
														class="motion-reduce:animate-none"
														aria-hidden="true"
													/>{:else}<Check class="size-4" aria-hidden="true" />{/if}
												{isSaving ? 'Saving...' : 'Save'}
											</Button>
											<IconButton label="Discard" disabled={isSaving} onclick={() => discard(item)}>
												<X />
											</IconButton>
										{/if}
										{#if item.source === 'instance'}
											<IconButton
												label="Reset to default"
												disabled={isSaving}
												onclick={() => reset(item)}
											>
												<RotateCcw />
											</IconButton>
										{/if}
									</div>
								{/if}
							</div>
						</li>
					{/each}
				</ul>
			</CollapsibleSection>
		{/each}
	{/if}
</Page>
