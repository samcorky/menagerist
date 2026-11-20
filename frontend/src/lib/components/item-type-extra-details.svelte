<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { promoteItemField, type NodeTypeResponse } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { getCore } from '$lib/field-types';
	import { fetchItemFields, type ItemField } from '$lib/item-fields';
	import { Button } from '$lib/components/ui/button/index.js';
	import ConfirmDialog from '$lib/components/confirm-dialog.svelte';

	// The extra details this type's items carry themselves, each one a click away from becoming
	// a field of the type. A quiet list in the editor, never a prompt (design §16b).
	let {
		type,
		onpromoted
	}: {
		type: NodeTypeResponse;
		/** The type as saved with the new field, and the field's key. */
		onpromoted: (updated: NodeTypeResponse, key: string) => void;
	} = $props();

	let fields = $state<ItemField[]>([]);
	let target = $state<ItemField | null>(null);
	let busy = $state(false);

	$effect(() => {
		const slug = type.slug;
		// A list that fails to load is left out: the editor works without it.
		void fetchItemFields(slug).then((found) => (fields = found ?? []));
	});

	const items = (count: number) => (count === 1 ? '1 item' : `${count.toLocaleString()} items`);

	async function promote() {
		if (!target) return;
		const field = target;
		busy = true;
		const result = await promoteItemField({
			path: { key: field.key },
			body: { node_type_id: type.id }
		});
		busy = false;
		if (result.error || !result.data) {
			toast.error(`Couldn't add ${field.label} to ${type.label}`, {
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
	<section class="space-y-2" aria-labelledby="extra-details-heading">
		<div>
			<h3 id="extra-details-heading" class="text-sm font-medium">Extra details on its items</h3>
			<p class="text-xs text-muted-foreground">
				Details added to single items. Add one to the item type to give every {type.label} item the field.
			</p>
		</div>
		<ul class="divide-y rounded-md border">
			{#each fields as field (`${field.key}:${field.kind}`)}
				<li class="flex items-center gap-3 px-3 py-2 text-sm">
					<div class="min-w-0 flex-1">
						<p class="truncate">{field.label}</p>
						<p class="text-xs text-muted-foreground">
							{getCore(field.kind)?.label ?? field.kind} · on {items(field.count)}
						</p>
					</div>
					<Button
						type="button"
						variant="outline"
						size="sm"
						aria-label={`Add ${field.label} to ${type.label}`}
						onclick={() => (target = field)}
					>
						Add to item type
					</Button>
				</li>
			{/each}
		</ul>
	</section>
{/if}

<ConfirmDialog
	open={target !== null}
	title={target ? `Add ${target.label} to ${type.label}?` : ''}
	description={target
		? `Every ${type.label} item gets the field. The ${items(target.count)} that have it now keep their values.`
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
