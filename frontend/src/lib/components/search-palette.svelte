<script lang="ts">
	import { tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { auth } from '$lib/auth.svelte.js';
	import { ArrowRight, Search } from '@lucide/svelte';
	import { collectionRouteParams } from '$lib/collections';
	import type { NodeTypeResponse } from '$lib/api/client';
	import { delayedLoading } from '$lib/delayed-loading.svelte';
	import { loadExampleIds } from '$lib/examples';
	import {
		loadItemTypes,
		searchEverything,
		type AsyncGroupKey,
		type GroupState,
		type Hit,
		type Results
	} from '$lib/palette-sources';
	import {
		descriptionSnippet,
		localScore,
		orderGroups,
		paletteLayout,
		settingPath,
		taskPath,
		type PaletteGroup,
		type StaticRoute
	} from '$lib/palette-search';
	import { groupLabel } from '$lib/settings-form';
	import { matchContext } from '$lib/search-context';
	import type { AttributesSchema } from '$lib/schema-types';
	import {
		collectionsAtCap,
		defaultHighlight,
		firstLiveValue,
		liveMessage,
		paletteView,
		resultSubtitle,
		seeAllCollectionsPath,
		seeAllSearch
	} from '$lib/search-palette';
	import { searchPaletteController } from '$lib/search-palette.svelte';
	import * as Command from '$lib/components/ui/command/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Spinner } from '$lib/components/ui/spinner/index.js';

	const DEBOUNCE_MS = 250;
	const SEE_ALL_VALUE = 'see-all-results';
	const SEE_ALL_COLLECTIONS_VALUE = 'see-all-collections';
	const ASYNC_KEYS: AsyncGroupKey[] = [
		'items',
		'collections',
		'itemTypes',
		'settings',
		'tasks',
		'collectionItems'
	];
	const GROUP_NOUN: Record<AsyncGroupKey, string> = {
		items: 'items',
		collections: 'collections',
		itemTypes: 'item types',
		settings: 'settings',
		tasks: 'scheduled tasks',
		collectionItems: 'items in this collection'
	};

	const emptyResults = (): Results => ({
		items: { status: 'ok', rows: [] },
		collections: { status: 'ok', rows: [] },
		itemTypes: { status: 'ok', rows: [] },
		settings: { status: 'ok', rows: [] },
		tasks: { status: 'ok', rows: [] },
		collectionItems: { status: 'ok', rows: [] },
		pages: []
	});

	// `inline` hosts the search in the top bar (field plus a results dropdown) instead of a sheet.
	let { inline = false }: { inline?: boolean } = $props();

	let query = $state('');
	let groups = $state<Results>(emptyResults());
	// Sources still waiting on an answer for the current query
	let loading = $state<AsyncGroupKey[]>([]);
	// Sources being re-run from their retry row
	let retrying = $state<AsyncGroupKey[]>([]);
	let itemsAnswered = $state(false);
	let debouncing = $state(false);
	let highlighted = $state('');
	// The row the popup chose itself; an arrow key moves the highlight off it
	let autoHighlight = '';
	let types = $state<NodeTypeResponse[]>([]);
	let exampleIds = $state<ReadonlySet<string>>(new Set());
	let inputEl = $state<HTMLInputElement | null>(null);
	let host = $state<HTMLElement | null>(null);
	// Where focus was before the inline field took it, so Escape can give it back.
	let returnTo: HTMLElement | null = null;
	let seq = 0;
	// Set when the popup closes to navigate, so focus is left for the new page.
	let navigating = false;

	// §13a: the 300 ms starts when the request does, not at the keystroke
	const spinner = delayedLoading();

	// What the person is looking at decides which groups come first.
	const layout = $derived(paletteLayout(page.url.pathname));
	const canSettings = $derived(auth.can('settings:instance:read'));
	const canTasks = $derived(auth.can('scheduling:job:read'));
	const hint = $derived(
		`Type to search items, collections, item types and pages${canSettings || canTasks ? ', settings and scheduled tasks' : ''}`
	);

	const pending = $derived(debouncing || loading.length > 0);
	const okRows = <T,>(state: GroupState<T>): T[] => (state.status === 'ok' ? state.rows : []);
	// The server marks items of the collection being viewed, and they show in their own group.
	const otherItems = $derived(okRows(groups.items));
	const showSeeAllCollections = $derived(collectionsAtCap(okRows(groups.collections).length));
	const failedKeys = $derived(
		ASYNC_KEYS.filter((key) => groups[key].status === 'error' && !loading.includes(key))
	);
	const count = $derived(
		otherItems.length +
			okRows(groups.collectionItems).length +
			okRows(groups.collections).length +
			okRows(groups.itemTypes).length +
			okRows(groups.settings).length +
			okRows(groups.tasks).length +
			groups.pages.length
	);
	const paletteState = $derived({
		query,
		pending,
		showSpinner: spinner.show,
		count,
		failed: failedKeys.length
	});
	const view = $derived(paletteView(paletteState));
	const announcement = $derived(liveMessage(paletteState));
	// Rows from an earlier query stay up until their source answers; they cannot be opened
	const staleKeys = $derived(debouncing ? [...ASYNC_KEYS, 'pages' as const] : loading);
	// The best match in each group decides the order; the page only breaks ties.
	const displayOrder = $derived.by(() => {
		const best: Partial<Record<PaletteGroup, number>> = {};
		const score = (key: PaletteGroup, rows: Hit[]) => {
			if (rows.length > 0) best[key] = Math.max(...rows.map((r) => r.score));
		};
		score('items', otherItems);
		score('collections', okRows(groups.collections));
		score('itemTypes', okRows(groups.itemTypes));
		score('settings', okRows(groups.settings));
		score('tasks', okRows(groups.tasks));
		score('collectionItems', okRows(groups.collectionItems));
		// Pages are matched in the browser, so it rates them on the server's scale.
		if (groups.pages.length > 0) {
			best.pages = Math.max(...groups.pages.map((r) => localScore(r.label, query)));
		}
		return orderGroups(layout.order, best);
	});
	// First row in display order that can be opened
	const firstValue = $derived(
		firstLiveValue(
			displayOrder.map((key) => ({
				values: rowValues(key),
				stale: staleKeys.includes(key)
			}))
		)
	);

	function rowValues(key: PaletteGroup): string[] {
		switch (key) {
			case 'items':
				return otherItems.map((r) => `item:${r.ref}`);
			case 'collectionItems':
				return okRows(groups.collectionItems).map((r) => `item:${r.ref}`);
			case 'collections':
				return [
					...okRows(groups.collections).map((r) => `collection:${r.ref}`),
					...(showSeeAllCollections ? [SEE_ALL_COLLECTIONS_VALUE] : [])
				];
			case 'itemTypes':
				return okRows(groups.itemTypes).map((r) => `type:${r.ref}`);
			case 'settings':
				return okRows(groups.settings).map((r) => `setting:${r.ref}`);
			case 'tasks':
				return okRows(groups.tasks).map((r) => `task:${r.ref}`);
			case 'pages':
				return groups.pages.map((r) => `page:${r.path}`);
		}
	}

	function typeOf(item: Hit): NodeTypeResponse | undefined {
		return types.find((t) => t.slug === item.group);
	}

	function subtitle(item: Hit): string {
		const type = typeOf(item);
		const schema = (type?.attributes_schema as AttributesSchema | null | undefined) ?? null;
		const found = { name: item.title, description: item.description, attributes: item.attributes };
		return resultSubtitle(type?.label ?? null, matchContext(found, schema, query));
	}

	function countLabel(n: number): string {
		return n === 1 ? '1 item' : `${n} items`;
	}

	function settleHighlight() {
		if (highlighted !== '' && highlighted !== autoHighlight) return;
		highlighted = defaultHighlight(firstValue, itemsAnswered, SEE_ALL_VALUE);
		autoHighlight = highlighted;
	}

	const isStale = (key: PaletteGroup) => staleKeys.includes(key);
	const retryBusy = (key: AsyncGroupKey) => debouncing || loading.includes(key);
	// An errored group shows its retry row; one hidden while a new query reloads it does not
	const showFailed = (key: AsyncGroupKey) =>
		groups[key].status === 'error' && (!loading.includes(key) || retrying.includes(key));

	function retry(key: AsyncGroupKey) {
		if (retryBusy(key)) return;
		retrying = [...retrying, key];
		run(query.trim(), [key]);
	}

	function run(text: string, only?: AsyncGroupKey[]) {
		const mine = only ? seq : ++seq;
		debouncing = false;
		if (!only) itemsAnswered = false;
		loading = [...new Set([...loading, ...(only ?? ASYNC_KEYS)])];
		spinner.set(true);
		void searchEverything(
			text,
			(partial) => {
				groups = { ...groups, ...partial };
				const settled = Object.keys(partial) as (keyof Results)[];
				loading = loading.filter((key) => !settled.includes(key));
				if (settled.includes('items')) itemsAnswered = true;
				if (retrying.some((key) => settled.includes(key))) {
					retrying = retrying.filter((key) => !settled.includes(key));
					// The retry row may unmount under the focused button
					void tick().then(() => {
						if (!document.activeElement || document.activeElement === document.body) {
							inputEl?.focus();
						}
					});
				}
				if (loading.length === 0) spinner.set(false);
				settleHighlight();
			},
			() => mine === seq,
			only,
			{ layout }
		);
	}

	// Debounced search; a blank query cancels anything in flight.
	$effect(() => {
		const text = query.trim();
		if (!searchPaletteController.open) return;
		if (!text) {
			seq++;
			debouncing = false;
			loading = [];
			retrying = [];
			spinner.set(false);
			groups = emptyResults();
			highlighted = '';
			autoHighlight = '';
			return;
		}
		const timer = setTimeout(() => run(text), DEBOUNCE_MS);
		debouncing = true;
		retrying = [];
		highlighted = SEE_ALL_VALUE;
		autoHighlight = SEE_ALL_VALUE;
		return () => clearTimeout(timer);
	});

	$effect(() => {
		if (!searchPaletteController.open) return;
		void loadItemTypes()
			.then((loaded) => (types = loaded))
			.catch(() => {});
		void loadExampleIds().then((ids) => (exampleIds = ids.items));
	});

	// A shortcut (or anything else) opening the inline search lands focus in its field.
	$effect(() => {
		if (!inline || !searchPaletteController.open || !inputEl) return;
		if (document.activeElement !== inputEl) {
			const active = document.activeElement;
			returnTo = active instanceof HTMLElement && active !== document.body ? active : null;
			inputEl.focus();
		}
	});

	// The field keeps focus after a result is opened, so focusing it again opens nothing: typing
	// into it has to bring the results back.
	$effect(() => {
		if (inline && query.trim() !== '' && !searchPaletteController.open) {
			searchPaletteController.show();
		}
	});

	function onInlineFocusIn() {
		if (!searchPaletteController.open) searchPaletteController.show();
	}

	// Judged a tick later: a row that unmounts under the focused button (a retry) drops focus to
	// the page for a moment before the palette puts it back in the field.
	let focusOutTimer: ReturnType<typeof setTimeout> | undefined;
	$effect(() => () => clearTimeout(focusOutTimer));

	function onInlineFocusOut() {
		clearTimeout(focusOutTimer);
		focusOutTimer = setTimeout(() => {
			if (!host?.contains(document.activeElement)) onOpenChange(false);
		}, 0);
	}

	// Escape first clears what was typed, then closes and hands focus back.
	function onInlineKeydown(event: KeyboardEvent) {
		if (event.key !== 'Escape') return;
		event.preventDefault();
		event.stopPropagation();
		if (query !== '') {
			query = '';
			return;
		}
		const back = returnTo;
		returnTo = null;
		inputEl?.blur();
		onOpenChange(false);
		back?.focus();
	}

	function onOpenChange(open: boolean) {
		if (open) {
			searchPaletteController.show();
			return;
		}
		searchPaletteController.hide();
		seq++;
		query = '';
		groups = emptyResults();
		loading = [];
		retrying = [];
		highlighted = '';
		autoHighlight = '';
		debouncing = false;
		spinner.set(false);
	}

	function choose(key: PaletteGroup, go: () => void) {
		if (isStale(key)) return seeAll();
		navigating = true;
		onOpenChange(false);
		go();
	}

	const openItem = (item: Hit, key: PaletteGroup = 'items') =>
		choose(key, () => void goto(resolve('/items/[id]', { id: item.ref })));
	const openCollection = (collection: Hit) =>
		choose(
			'collections',
			() =>
				void goto(
					resolve(
						'/collections/[id]',
						collectionRouteParams({ id: collection.ref, slug: collection.slug ?? collection.ref })
					)
				)
		);
	// Built before choose() closes the popup, which clears the query
	const openAllCollections = () => {
		const path = seeAllCollectionsPath(query);
		choose('collections', () => void goto(resolve(path)));
	};
	const openItemType = (slug: string) =>
		choose(
			'itemTypes',
			() => void goto(resolve(`/items?${new URLSearchParams({ type: slug }).toString()}`))
		);
	const openPage = (path: StaticRoute) => choose('pages', () => void goto(resolve(path)));
	const openSetting = (setting: Hit) =>
		choose(
			'settings',
			() => void goto(resolve(settingPath({ key: setting.ref, group: setting.group ?? '' })))
		);
	const openTask = (task: Hit) =>
		choose('tasks', () => void goto(resolve(taskPath({ job_key: task.ref }))));

	function seeAll() {
		const search = seeAllSearch(query);
		navigating = true;
		onOpenChange(false);
		void goto(resolve(`/items?${search}`));
	}
</script>

{#snippet failedRow(key: AsyncGroupKey)}
	<div class="flex items-center justify-between gap-2 px-2 text-sm pointer-coarse:min-h-11">
		<span class="text-muted-foreground">Couldn't search {GROUP_NOUN[key]}</span>
		<!-- aria-disabled, not disabled, so focus stays on the button while it reloads -->
		<Button
			variant="outline"
			class={['pointer-coarse:min-h-11', retryBusy(key) && 'opacity-50']}
			aria-label={`Try searching ${GROUP_NOUN[key]} again`}
			aria-disabled={retryBusy(key)}
			onclick={() => retry(key)}
			onkeydown={(e) => {
				// Command.Root would otherwise treat Enter as selecting the highlighted row
				if (e.key === 'Enter') e.stopPropagation();
			}}
		>
			{retrying.includes(key) ? 'Retrying…' : 'Try again'}
		</Button>
	</div>
{/snippet}

{#snippet itemGroup(key: 'items' | 'collectionItems', heading: string, rows: Hit[])}
	{#if showFailed(key)}
		<Command.Group {heading}>{@render failedRow(key)}</Command.Group>
	{:else if rows.length > 0}
		<Command.Group {heading}>
			{#each rows as item (item.ref)}
				{@const sub = subtitle(item)}
				<Command.Item
					disabled={isStale(key)}
					value={`item:${item.ref}`}
					class="pointer-coarse:min-h-11"
					onSelect={() => openItem(item, key)}
				>
					<div class="min-w-0 flex-1">
						<div class="flex items-center gap-2">
							<span class="truncate font-medium">{item.title}</span>
							{#if exampleIds.has(item.ref)}
								<Badge variant="outline" class="shrink-0 text-muted-foreground">Example</Badge>
							{/if}
						</div>
						{#if sub}
							<p class="truncate text-xs text-muted-foreground">{sub}</p>
						{/if}
					</div>
				</Command.Item>
			{/each}
		</Command.Group>
	{/if}
{/snippet}

{#snippet collectionsGroup()}
	{#if showFailed('collections')}
		<Command.Group heading="Collections">{@render failedRow('collections')}</Command.Group>
	{:else if okRows(groups.collections).length > 0}
		<Command.Group heading="Collections">
			{#each okRows(groups.collections) as collection (collection.ref)}
				<Command.Item
					disabled={isStale('collections')}
					value={`collection:${collection.ref}`}
					class="pointer-coarse:min-h-11"
					onSelect={() => openCollection(collection)}
				>
					<div class="min-w-0 flex-1">
						<span class="block truncate font-medium">{collection.title}</span>
						<p class="truncate text-xs text-muted-foreground">
							{countLabel(collection.item_count ?? 0)}
						</p>
					</div>
				</Command.Item>
			{/each}
			{#if showSeeAllCollections}
				<Command.Item
					disabled={isStale('collections')}
					value={SEE_ALL_COLLECTIONS_VALUE}
					class="pointer-coarse:min-h-11"
					onSelect={openAllCollections}
				>
					<Search class="size-4" />
					<span class="flex-1">See all collections</span>
					<ArrowRight class="size-4" />
				</Command.Item>
			{/if}
		</Command.Group>
	{/if}
{/snippet}

{#snippet itemTypesGroup()}
	{#if showFailed('itemTypes')}
		<Command.Group heading="Item types">{@render failedRow('itemTypes')}</Command.Group>
	{:else if okRows(groups.itemTypes).length > 0}
		<Command.Group heading="Item types">
			{#each okRows(groups.itemTypes) as type (type.ref)}
				<Command.Item
					disabled={isStale('itemTypes')}
					value={`type:${type.ref}`}
					class="pointer-coarse:min-h-11"
					onSelect={() => openItemType(type.ref)}
				>
					<div class="min-w-0 flex-1">
						<span class="block truncate font-medium">{type.title}</span>
						<p class="truncate text-xs text-muted-foreground">Item type</p>
					</div>
				</Command.Item>
			{/each}
		</Command.Group>
	{/if}
{/snippet}

{#snippet settingsGroup()}
	{#if showFailed('settings')}
		<Command.Group heading="Settings">{@render failedRow('settings')}</Command.Group>
	{:else if okRows(groups.settings).length > 0}
		<Command.Group heading="Settings">
			{#each okRows(groups.settings) as setting (setting.ref)}
				<Command.Item
					disabled={isStale('settings')}
					value={`setting:${setting.ref}`}
					class="pointer-coarse:min-h-11"
					onSelect={() => openSetting(setting)}
				>
					<div class="min-w-0 flex-1">
						<span class="block truncate font-medium">{setting.title}</span>
						<p class="truncate text-xs text-muted-foreground">
							Setting · {groupLabel(setting.group ?? '')}
						</p>
						{#if descriptionSnippet(setting.title, setting.description, query)}
							<p class="truncate text-xs text-muted-foreground">
								{descriptionSnippet(setting.title, setting.description, query)}
							</p>
						{/if}
					</div>
				</Command.Item>
			{/each}
		</Command.Group>
	{/if}
{/snippet}

{#snippet tasksGroup()}
	{#if showFailed('tasks')}
		<Command.Group heading="Scheduled tasks">{@render failedRow('tasks')}</Command.Group>
	{:else if okRows(groups.tasks).length > 0}
		<Command.Group heading="Scheduled tasks">
			{#each okRows(groups.tasks) as task (task.ref)}
				<Command.Item
					disabled={isStale('tasks')}
					value={`task:${task.ref}`}
					class="pointer-coarse:min-h-11"
					onSelect={() => openTask(task)}
				>
					<div class="min-w-0 flex-1">
						<span class="block truncate font-medium">{task.title}</span>
						<p class="truncate text-xs text-muted-foreground">Scheduled task</p>
						{#if descriptionSnippet(task.title, task.description, query)}
							<p class="truncate text-xs text-muted-foreground">
								{descriptionSnippet(task.title, task.description, query)}
							</p>
						{/if}
					</div>
				</Command.Item>
			{/each}
		</Command.Group>
	{/if}
{/snippet}

{#snippet pagesGroup()}
	{#if groups.pages.length > 0}
		<Command.Group heading="Pages">
			{#each groups.pages as page (page.path)}
				<Command.Item
					disabled={isStale('pages')}
					value={`page:${page.path}`}
					class="pointer-coarse:min-h-11"
					onSelect={() => openPage(page.path)}
				>
					<div class="min-w-0 flex-1">
						<span class="block truncate font-medium">{page.label}</span>
						<p class="truncate text-xs text-muted-foreground">Page</p>
					</div>
				</Command.Item>
			{/each}
		</Command.Group>
	{/if}
{/snippet}

{#snippet results()}
	{#if view === 'hint'}
		<p class="py-6 text-center text-sm text-muted-foreground" aria-hidden="true">
			{hint}
		</p>
	{:else if view === 'loading'}
		<div class="flex justify-center py-6" aria-hidden="true">
			<Spinner class="size-5" />
		</div>
	{:else if view === 'empty'}
		<p class="py-6 text-center text-sm text-muted-foreground" aria-hidden="true">
			Nothing found for "{query.trim()}"
		</p>
	{/if}
	{#if view !== 'hint'}
		<Command.List class={inline ? 'max-h-[60dvh]' : 'mt-2 max-h-[50dvh]'}>
			{#each displayOrder as key (key)}
				{#if key === 'items'}
					{@render itemGroup('items', 'Items', otherItems)}
				{:else if key === 'collectionItems'}
					{@render itemGroup(
						'collectionItems',
						'In this collection',
						okRows(groups.collectionItems)
					)}
				{:else if key === 'collections'}
					{@render collectionsGroup()}
				{:else if key === 'itemTypes'}
					{@render itemTypesGroup()}
				{:else if key === 'settings'}
					{@render settingsGroup()}
				{:else if key === 'tasks'}
					{@render tasksGroup()}
				{:else}
					{@render pagesGroup()}
				{/if}
			{/each}
			<Command.Item value={SEE_ALL_VALUE} class="pointer-coarse:min-h-11" onSelect={seeAll}>
				<Search class="size-4" />
				<span class="flex-1">See all results in Items</span>
				<ArrowRight class="size-4" />
			</Command.Item>
		</Command.List>
	{/if}
{/snippet}

{#snippet panel()}
	<Command.Root
		shouldFilter={false}
		loop
		bind:value={highlighted}
		class={inline ? 'overflow-visible rounded-none bg-transparent p-0' : 'mt-3 bg-transparent p-0'}
	>
		<Command.Input
			bind:ref={inputEl}
			bind:value={query}
			placeholder="Search everything…"
			aria-label="Search"
			wrapperClass={inline ? 'p-0' : undefined}
			class="pointer-coarse:h-11"
		/>
		<p class="sr-only" role="status" aria-live="polite">{announcement}</p>
		{#if inline}
			{#if searchPaletteController.open}
				<!-- mousedown would blur the field and close the results before a click lands -->
				<div
					class="absolute inset-x-0 top-full z-50 mt-1 max-h-[70dvh] overflow-y-auto rounded-2xl border bg-popover p-1 text-popover-foreground shadow-lg"
					onmousedown={(event) => event.preventDefault()}
					role="presentation"
				>
					{@render results()}
				</div>
			{/if}
		{:else}
			{@render results()}
		{/if}
	</Command.Root>
{/snippet}

{#if inline}
	<!-- The listeners only watch focus and Escape bubbling up from the field inside. -->
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<div
		bind:this={host}
		role="search"
		aria-label="Search"
		data-search-inline
		data-state={searchPaletteController.open ? 'open' : 'closed'}
		class="relative w-full"
		onfocusin={onInlineFocusIn}
		onfocusout={onInlineFocusOut}
		onkeydown={onInlineKeydown}
	>
		{@render panel()}
	</div>
{:else}
	<ResponsiveDialog.Root open={searchPaletteController.open} {onOpenChange}>
		<ResponsiveDialog.Content
			title="Search"
			size="lg"
			onOpenAutoFocus={(e) => {
				e.preventDefault();
				inputEl?.focus();
			}}
			onCloseAutoFocus={(e) => {
				if (!navigating) return;
				navigating = false;
				e.preventDefault();
			}}
		>
			{@render panel()}
		</ResponsiveDialog.Content>
	</ResponsiveDialog.Root>
{/if}
