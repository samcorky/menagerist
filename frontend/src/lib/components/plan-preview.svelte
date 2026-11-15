<script lang="ts">
	import { LISTED, summarisePlan, type ImportPlan, type PlanGroup } from '$lib/import-plan';
	import { Button } from '$lib/components/ui/button/index.js';

	let {
		plan,
		loading = false,
		error = null,
		busy = false,
		confirmLabel = 'Add',
		busyLabel = 'Adding…',
		onCancel,
		onConfirm
	}: {
		/** What going ahead would do; null while it is being worked out. */
		plan: ImportPlan | null;
		loading?: boolean;
		/** Why the preview could not be worked out. */
		error?: string | null;
		busy?: boolean;
		confirmLabel?: string;
		busyLabel?: string;
		onCancel: () => void;
		onConfirm: () => void;
	} = $props();

	const summary = $derived(plan ? summarisePlan(plan) : null);
	const stuck = $derived(
		summary !== null && (summary.blockers.length > 0 || summary.conflicts.length > 0)
	);
	const haveShown = $derived(summary ? summary.have.slice(0, LISTED) : []);

	function detail(group: PlanGroup): string {
		if (group.names.length === 0) return '';
		const more = group.more > 0 ? ` and ${group.more} more` : '';
		return `: ${group.names.join(', ')}${more}`;
	}
</script>

<div class="space-y-4">
	{#if loading}
		<p class="py-4 text-center text-sm text-muted-foreground">Checking what this will add…</p>
	{:else if error}
		<p class="text-sm text-destructive" role="alert">{error}</p>
	{:else if summary}
		{#if stuck}
			<section class="space-y-1" aria-label="What stops this">
				<h3 class="text-sm font-medium">This can't go ahead</h3>
				<ul class="space-y-1 text-sm text-destructive" role="alert">
					{#each summary.blockers as blocker (blocker.code + blocker.reason)}
						<li>{blocker.reason}</li>
					{/each}
					{#each summary.conflicts as conflict (conflict.kind + conflict.ref)}
						<li>{conflict.reason ?? conflict.label}</li>
					{/each}
				</ul>
			</section>
		{/if}
		{#if summary.adding.length > 0}
			<section class="space-y-1" aria-label="What will be added">
				<h3 class="text-sm font-medium">Will be added</h3>
				<ul class="space-y-1 text-sm">
					{#each summary.adding as group (group.kind)}
						<li>
							<span class="font-medium">{group.heading}</span><span class="text-muted-foreground"
								>{detail(group)}</span
							>
						</li>
					{/each}
				</ul>
			</section>
		{:else if !stuck}
			<p class="text-sm text-muted-foreground">You already have everything here.</p>
		{/if}
		{#if summary.have.length > 0}
			<section class="space-y-1" aria-label="What you already have">
				<h3 class="text-sm font-medium">You already have</h3>
				<ul class="space-y-1 text-sm text-muted-foreground">
					{#each haveShown as entity (entity.kind + entity.ref)}
						<li>{entity.label}{entity.reason ? ` · ${entity.reason}` : ''}</li>
					{/each}
					{#if summary.have.length > haveShown.length}
						<li>and {summary.have.length - haveShown.length} more</li>
					{/if}
				</ul>
			</section>
		{/if}
	{/if}
	<div class="flex justify-end gap-2">
		<Button
			type="button"
			variant="outline"
			class="pointer-coarse:h-11"
			disabled={busy}
			onclick={onCancel}
		>
			Cancel
		</Button>
		{#if summary?.canAdd}
			<Button type="button" class="pointer-coarse:h-11" disabled={busy} onclick={onConfirm}>
				{busy ? busyLabel : confirmLabel}
			</Button>
		{/if}
	</div>
</div>
