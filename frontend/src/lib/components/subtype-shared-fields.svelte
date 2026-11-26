<script lang="ts">
	import { toast } from 'svelte-sonner';
	import {
		listSharedSubtypeFields,
		promoteSubtypeField,
		type NodeTypeResponse,
		type SharedSubtypeFieldResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { getCore } from '$lib/field-types';
	import { Button } from '$lib/components/ui/button/index.js';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';

	// The fields several subtypes of this type each define themselves, each one a click away from
	// moving up to the type so they stop repeating. A quiet list in the editor, never a prompt
	// (design §16b).
	let {
		type,
		types,
		onpromoted
	}: {
		/** The parent type being edited. */
		type: NodeTypeResponse;
		/** Every item type, to name the subtypes. */
		types: NodeTypeResponse[];
		/** The parent as saved with the new field, and the field's key. */
		onpromoted: (updated: NodeTypeResponse, key: string) => void;
	} = $props();

	let fields = $state<SharedSubtypeFieldResponse[]>([]);
	let target = $state<SharedSubtypeFieldResponse | null>(null);
	let busy = $state(false);

	$effect(() => {
		const id = type.id;
		// A list that fails to load is left out: the editor works without it.
		void listSharedSubtypeFields({ path: { node_type_id: id } }).then(
			(result) => (fields = result.data ?? [])
		);
	});

	const labelOf = (slug: string) => types.find((t) => t.slug === slug)?.label ?? slug;
	const names = (slugs: readonly string[]) => slugs.map(labelOf).join(', ');
	const subtypes = (count: number) => (count === 1 ? '1 subtype' : `${count} subtypes`);

	async function promote() {
		if (!target) return;
		const field = target;
		busy = true;
		const result = await promoteSubtypeField({
			path: { node_type_id: type.id, key: field.key }
		});
		busy = false;
		if (result.error || !result.data) {
			toast.error(`Couldn't move ${field.label} to ${type.label}`, {
				description: errorMessage(result.error)
			});
			return;
		}
		target = null;
		fields = fields.filter((f) => f.key !== field.key);
		toast.success(`${field.label} is now a field of ${type.label}`);
		onpromoted(result.data.node_type, field.key);
	}
</script>

{#if fields.length > 0}
	<section
		class="space-y-2"
		aria-labelledby="subtype-fields-heading"
		data-testid="subtype-shared-fields"
	>
		<div>
			<h3 id="subtype-fields-heading" class="text-sm font-medium">Fields its subtypes share</h3>
			<p class="text-xs text-muted-foreground">
				Fields several subtypes each define for themselves. Add one to {type.label} to define it once
				for all of them.
			</p>
		</div>
		<ul class="divide-y rounded-md border">
			{#each fields as field (field.key)}
				<li class="flex items-center gap-3 px-3 py-2 text-sm">
					<div class="min-w-0 flex-1">
						<p class="truncate">{field.label}</p>
						<p class="text-xs text-muted-foreground">
							{getCore(field.kind ?? '')?.label ?? field.kind} · on {subtypes(
								field.subtypes.length
							)}:
							{names(field.subtypes)}
						</p>
						{#if field.differing.length > 0}
							<p class="text-xs text-muted-foreground">
								{names(field.differing)}
								{field.differing.length === 1 ? 'keeps' : 'keep'} it as a different kind of field, so
								it cannot move up yet.
							</p>
						{/if}
					</div>
					{#if field.differing.length === 0}
						<Button
							type="button"
							variant="outline"
							size="sm"
							aria-label={`Add ${field.label} to ${type.label}`}
							onclick={() => (target = field)}
						>
							Add to parent type
						</Button>
					{/if}
				</li>
			{/each}
		</ul>
	</section>
{/if}

<ConfirmDialog
	open={target !== null}
	title={target ? `Add ${target.label} to ${type.label}?` : ''}
	description={target
		? `${type.label} gets the field, and ${names(target.subtypes)} stop defining their own. Their items keep every value. Where it is a list of choices, the options are combined.`
		: undefined}
	destructive={false}
	{busy}
	busyLabel="Adding…"
	confirmLabel="Add field"
	onOpenChange={(open) => {
		if (!open) target = null;
	}}
	onConfirm={() => void promote()}
/>
