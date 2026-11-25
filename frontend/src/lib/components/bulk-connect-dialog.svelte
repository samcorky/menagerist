<script lang="ts">
	import { toast } from 'svelte-sonner';
	import {
		createEdges,
		listEdgeTypes,
		listNodes,
		listNodeTypes,
		type EdgeTypeResponse,
		type NodeResponse,
		type NodeTypeResponse
	} from '$lib/api/client';
	import { errorMessage, networkAwareError } from '$lib/api/errors';
	import { itemCount, unknownItemIds } from '$lib/bulk-actions';
	import { allowsItemType, parentsByType } from '$lib/connection-limits';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';

	let {
		open,
		ids,
		onOpenChange,
		ondone,
		onmissing
	}: {
		open: boolean;
		ids: string[];
		onOpenChange: (open: boolean) => void;
		ondone: () => void;
		onmissing: (ids: string[]) => void;
	} = $props();

	let types = $state<EdgeTypeResponse[] | null>(null);
	let itemTypes = $state<NodeTypeResponse[]>([]);
	let typeSlug = $state('');
	let search = $state('');
	let results = $state<NodeResponse[]>([]);
	let target = $state<NodeResponse | null>(null);
	let sending = $state(false);
	let error = $state<string | null>(null);
	let seq = 0;

	// The shared item cannot be one of the selection: an item is never connected to itself.
	// Each selected item starts its own connection, so the shared item is the target end: only
	// items that end allows are offered. The selected items' own types are checked by the server.
	const chosenType = $derived(types?.find((t) => t.slug === typeSlug) ?? null);
	// Changing the connection after picking an item can leave that item outside the limit.
	// A limit on a parent type covers its subtypes.
	const parentOfType = $derived(parentsByType(itemTypes));
	const targetFits = $derived(
		!target || allowsItemType(chosenType?.target_types, target.type, parentOfType)
	);
	const choices = $derived(
		results.filter(
			(r) => !ids.includes(r.id) && allowsItemType(chosenType?.target_types, r.type, parentOfType)
		)
	);

	$effect(() => {
		if (!open) return;
		typeSlug = '';
		search = '';
		results = [];
		target = null;
		error = null;
		void listEdgeTypes({ query: { limit: 100 } }).then((r) => {
			types = r.data ?? [];
		});
		void listNodeTypes({ query: { limit: 200 } }).then((r) => {
			itemTypes = r.data ?? [];
		});
	});

	$effect(() => {
		if (!open) return;
		const text = search;
		// A single allowed type is asked of the server, so a full page of other items cannot hide
		// it. A parent type is not, since the server matches a type exactly, not its subtypes.
		const allowed = chosenType?.target_types ?? [];
		const isParent = allowed.length === 1 && [...parentOfType.values()].includes(allowed[0]);
		const type = allowed.length === 1 && !isParent ? allowed[0] : undefined;
		const mine = ++seq;
		const timer = setTimeout(
			async () => {
				const r = await listNodes({ query: { limit: 20, q: text || undefined, type } });
				if (mine === seq && r.data) results = r.data;
			},
			text ? 250 : 0
		);
		return () => clearTimeout(timer);
	});

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		if (sending || !target || !typeSlug || !targetFits) return;
		sending = true;
		error = null;
		// Many items to one: each selected item is the start of its own connection into the target.
		const result = await createEdges({
			body: { source_id: target.id, target_ids: ids, type: typeSlug, reverse: true }
		});
		sending = false;
		if (result.error || !result.data) {
			if (!result.response) {
				const { title, description } = networkAwareError(result);
				toast.error(title, { description });
				return;
			}
			const detail = errorMessage(result.error);
			error = detail;
			const missing = unknownItemIds(detail);
			if (missing.length > 0) onmissing(missing);
			return;
		}
		const { created, skipped } = result.data;
		toast.success(
			skipped.length > 0
				? `Connected ${itemCount(created.length)} (${skipped.length} already were)`
				: `Connected ${itemCount(created.length)}`
		);
		ondone();
		onOpenChange(false);
	}
</script>

<ResponsiveDialog.Root {open} onOpenChange={(value) => !sending && onOpenChange(value)}>
	<ResponsiveDialog.Content title="Connect {itemCount(ids.length)} to one item">
		<form class="mt-4 space-y-4" onsubmit={submit}>
			{#if types !== null && types.length === 0}
				<p class="text-sm text-muted-foreground">
					You have no connection types yet. Connect two items from an item's page first.
				</p>
			{:else}
				<div class="space-y-1.5">
					<Label for="bulk-connect-type">Connection</Label>
					<NativeSelect.Root id="bulk-connect-type" bind:value={typeSlug} disabled={types === null}>
						<NativeSelect.Option value="">Choose a connection</NativeSelect.Option>
						{#each types ?? [] as type (type.slug)}
							<NativeSelect.Option value={type.slug}>{type.label}</NativeSelect.Option>
						{/each}
					</NativeSelect.Root>
				</div>
				<div class="space-y-1.5">
					<Label for="bulk-connect-search">To this item</Label>
					<Input
						id="bulk-connect-search"
						type="search"
						bind:value={search}
						placeholder="Search your items…"
						autocomplete="off"
					/>
					<ul
						class="max-h-48 divide-y overflow-y-auto rounded-md border"
						aria-label="Matching items"
					>
						{#each choices as choice (choice.id)}
							<li>
								<label
									class="flex cursor-pointer items-center gap-3 px-3 py-2 text-sm pointer-coarse:min-h-11"
								>
									<input
										type="radio"
										name="bulk-connect-target"
										class="size-4 shrink-0 accent-primary"
										checked={target?.id === choice.id}
										onchange={() => (target = choice)}
										aria-label="Connect to {choice.name}"
									/>
									<span class="min-w-0 flex-1 truncate">{choice.name}</span>
								</label>
							</li>
						{:else}
							<li class="p-3 text-sm text-muted-foreground">No matching items.</li>
						{/each}
					</ul>
				</div>
				{#if target && chosenType && targetFits}
					<p class="text-sm text-muted-foreground" aria-live="polite">
						{itemCount(ids.length)}: {chosenType.label}
						{target.name}
					</p>
				{:else if target && chosenType}
					<p class="text-sm text-muted-foreground" aria-live="polite">
						{chosenType.label} doesn't connect to {target.name}. Pick another item.
					</p>
				{/if}
			{/if}
			{#if error}
				<p role="alert" class="text-sm text-destructive">{error}</p>
			{/if}
			<div class="flex justify-end gap-2">
				<Button type="button" variant="outline" onclick={() => onOpenChange(false)}>Cancel</Button>
				<Button type="submit" disabled={sending || !target || !typeSlug || !targetFits}>
					{sending ? 'Connecting…' : 'Connect'}
				</Button>
			</div>
		</form>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
