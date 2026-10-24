<script lang="ts">
	import { Plus } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as NativeSelect from '$lib/components/ui/native-select/index.js';
	import QueryGroup from '$lib/components/query-group.svelte';
	import QueryItemPicker from '$lib/components/query-item-picker.svelte';
	import {
		ANY_RELATIONSHIP_LABEL,
		directionChoices,
		relationshipOptionLabel,
		withConnectionDirection,
		withConnectionFilter,
		withConnectionItem,
		withConnectionRelationship,
		type BuilderView
	} from '$lib/query/builder';
	import { FAR_END, type Condition, type Path } from '$lib/query/types';

	type ConnectionRow = Extract<Condition, { kind: 'connection' }>;

	let {
		condition,
		path,
		name,
		view,
		onchange
	}: {
		condition: ConnectionRow;
		path: Path;
		/** The row's accessible name, e.g. "Condition 2". */
		name: string;
		view: BuilderView;
		onchange: (condition: Condition) => void;
	} = $props();

	const relationship = $derived(
		condition.relationship
			? (view.relationships?.find((r) => r.slug === condition.relationship) ?? null)
			: null
	);
	// A relationship that is not in the list (yet, or any more) stays selectable so the row can show it.
	const unlisted = $derived(condition.relationship !== undefined && relationship === null);
	// No relationship, or one the list does not know, leaves the direction open.
	const directions = $derived(directionChoices(relationship));

	function onRelationship(slug: string) {
		const chosen = view.relationships?.find((r) => r.slug === slug) ?? null;
		onchange(withConnectionRelationship(condition, chosen));
	}
</script>

<div class="flex flex-col gap-2">
	<div class="flex flex-wrap items-center gap-2">
		<NativeSelect.Root
			class="min-w-0 flex-1 basis-48 sm:max-w-72 [&_select]:h-9"
			aria-label="{name}, relationship"
			value={condition.relationship ?? ''}
			onchange={(e) => onRelationship(e.currentTarget.value)}
		>
			<NativeSelect.Option value="">{ANY_RELATIONSHIP_LABEL}</NativeSelect.Option>
			{#if unlisted && condition.relationship}
				<NativeSelect.Option value={condition.relationship}>
					{view.relationships === null
						? 'Loading relationships…'
						: `${condition.relationship} (no longer exists)`}
				</NativeSelect.Option>
			{/if}
			{#each view.relationships ?? [] as r (r.slug)}
				<NativeSelect.Option value={r.slug}>{relationshipOptionLabel(r)}</NativeSelect.Option>
			{/each}
		</NativeSelect.Root>
		{#if directions.length > 0}
			<NativeSelect.Root
				class="min-w-0 flex-1 basis-36 sm:max-w-48 [&_select]:h-9"
				aria-label="{name}, direction"
				value={condition.direction ?? 'any'}
				onchange={(e) =>
					onchange(
						withConnectionDirection(condition, e.currentTarget.value as 'any' | 'out' | 'in')
					)}
			>
				{#each directions as d (d.value)}
					<NativeSelect.Option value={d.value}>{d.label}</NativeSelect.Option>
				{/each}
			</NativeSelect.Root>
		{/if}
	</div>

	{#if view.relationshipsFailed}
		<div class="flex flex-wrap items-center gap-2">
			<p role="alert" class="text-sm text-destructive">Could not load your relationships.</p>
			<Button
				variant="outline"
				size="sm"
				class="min-h-9"
				aria-label="{name}, retry loading relationships"
				onclick={() => view.retryRelationships()}>Retry</Button
			>
		</div>
	{/if}

	{#if condition.mode === 'to'}
		<QueryItemPicker
			itemId={condition.item}
			label="{name}, item"
			{view}
			onpick={(id) => onchange(withConnectionItem(condition, id))}
		/>
	{:else if condition.where}
		<div class="flex flex-col gap-2">
			<p class="text-sm font-medium">Where the linked item…</p>
			<QueryGroup group={condition.where} path={[...path, FAR_END]} {view} />
		</div>
	{:else}
		<Button
			variant="outline"
			size="sm"
			class="min-h-9 w-fit"
			disabled={!view.canAddCondition}
			aria-label="{name}, filter the linked item"
			onclick={() => onchange(withConnectionFilter(condition, true))}
		>
			<Plus />
			Where the linked item…
		</Button>
	{/if}
</div>
