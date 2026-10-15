<script lang="ts">
	import { FolderPlus, Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import QueryConditionRow from '$lib/components/query-condition-row.svelte';
	import QueryGroup from '$lib/components/query-group.svelte';
	import { MAX_CONDITIONS, MAX_DEPTH } from '$lib/query/limits';
	import { pathKey } from '$lib/query/warnings';
	import { isGroup, type Group, type Path } from '$lib/query/types';
	import { firstConditionPath, type BuilderView } from '$lib/query/builder';

	let { group, path, view }: { group: Group; path: Path; view: BuilderView } = $props();

	const hintId = $props.id();

	const isRoot = $derived(path.length === 0);
	const isNot = $derived(group.op === 'not');
	const canAddCondition = $derived(view.canAddCondition && !(isNot && group.children.length > 0));
	const canAddGroup = $derived(canAddCondition && view.canAddGroup(path));
	const conditionHint = $derived(
		view.canAddCondition
			? 'This group holds one condition.'
			: `A filter can have up to ${MAX_CONDITIONS} conditions.`
	);
	const groupHint = $derived(
		!canAddCondition ? conditionHint : `Groups can go ${MAX_DEPTH - 1} levels deep.`
	);
	const firstNumber = $derived(view.numbers.get(pathKey(firstConditionPath(group, path))));
	const groupName = $derived(
		isRoot ? 'All conditions' : firstNumber ? `Group from condition ${firstNumber}` : 'New group'
	);
	const hint = $derived(!canAddCondition ? conditionHint : !canAddGroup ? groupHint : null);

	const segment =
		'min-h-9 px-3 text-sm font-medium transition-colors focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none';
</script>

<section
	class={isRoot ? 'flex flex-col gap-3' : 'flex flex-col gap-3 rounded-xl border border-dashed p-3'}
	aria-label={groupName}
>
	<div class="flex flex-wrap items-center gap-2 text-sm">
		{#if isNot}
			<span class="font-medium">Must not match</span>
		{:else}
			<span>Match</span>
			<div
				role="group"
				aria-label="{groupName}: match all or any"
				class="inline-flex overflow-hidden rounded-md border border-input"
			>
				{#each [{ op: 'and', label: 'all' }, { op: 'or', label: 'any' }] as const as choice (choice.op)}
					<button
						type="button"
						aria-pressed={group.op === choice.op}
						class="{segment} {choice.op === 'or' ? 'border-l border-input' : ''} {group.op ===
						choice.op
							? 'bg-primary text-primary-foreground'
							: 'bg-background hover:bg-accent'}"
						onclick={() => view.setGroupOp(path, choice.op)}
					>
						{choice.label}
					</button>
				{/each}
			</div>
			<span>of these</span>
		{/if}
		{#if !isRoot}
			<Button
				variant="ghost"
				size="icon"
				class="ml-auto"
				aria-label="Remove {groupName.toLowerCase()}"
				onclick={() => view.remove(path)}
			>
				<X />
			</Button>
		{/if}
	</div>

	{#if group.children.length > 0}
		<ul class="flex flex-col gap-2">
			{#each group.children as child, i (`${pathKey([...path, i])}:${isGroup(child) ? 'g' : 'c'}`)}
				{#if isGroup(child)}
					<li><QueryGroup group={child} path={[...path, i]} {view} /></li>
				{:else}
					<QueryConditionRow condition={child} path={[...path, i]} {view} />
				{/if}
			{/each}
		</ul>
	{:else}
		<p class="text-sm text-muted-foreground">No conditions yet.</p>
	{/if}

	{#if !(isNot && group.children.length > 0)}
		<div class="flex flex-wrap gap-2">
			<Button
				variant="outline"
				size="sm"
				class="min-h-9"
				data-add-condition
				disabled={!canAddCondition}
				aria-describedby={hint && !canAddCondition ? hintId : undefined}
				onclick={() => view.addCondition(path)}
			>
				<Plus />
				Add condition
			</Button>
			<Button
				variant="outline"
				size="sm"
				class="min-h-9"
				disabled={!canAddGroup}
				aria-describedby={hint && !canAddGroup ? hintId : undefined}
				onclick={() => view.addGroup(path)}
			>
				<FolderPlus />
				Add group
			</Button>
		</div>
		{#if hint}
			<p id={hintId} class="text-xs text-muted-foreground">{hint}</p>
		{/if}
	{/if}
</section>
