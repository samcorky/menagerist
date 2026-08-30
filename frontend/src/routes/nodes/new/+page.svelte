<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { createNode, listNodeTypes } from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import AttributesEditor, {
		attributesToRows,
		rowsToAttributes,
		type AttributeRow
	} from '$lib/components/attributes-editor.svelte';
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';

	let name = $state('');
	let type = $state('');
	let description = $state('');
	let attributeRows = $state<AttributeRow[]>(attributesToRows({}));
	let submitting = $state(false);
	let knownTypeSlugs = $state<string[]>([]);

	$effect(() => {
		listNodeTypes({ query: { limit: 200 } }).then((result) => {
			if (result.data) {
				knownTypeSlugs = result.data.map((t) => t.slug);
			}
		});
	});

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		submitting = true;

		const result = await createNode({
			body: {
				name,
				type,
				description: description || null,
				attributes: rowsToAttributes(attributeRows)
			}
		});

		if (result.error || !result.data) {
			toast.error("Couldn't create node", { description: errorMessage(result.error) });
			submitting = false;
			return;
		}

		await goto(resolve('/nodes/[id]', { id: result.data.id }));
	}
</script>

<svelte:head>
	<title>New Node</title>
</svelte:head>

<main class="flex-1 bg-background px-6 py-10 text-foreground">
	<div class="mx-auto max-w-2xl">
		<Card.Root>
			<Card.Header>
				<Card.Title>New Node</Card.Title>
				<Card.Description>Add a new item to your collection graph.</Card.Description>
			</Card.Header>
			<Card.Content>
				<form class="space-y-4" onsubmit={handleSubmit}>
					<div class="space-y-2">
						<Label for="name">Name</Label>
						<Input id="name" bind:value={name} required />
					</div>

					<div class="space-y-2">
						<Label for="type">Type</Label>
						<Input
							id="type"
							bind:value={type}
							required
							placeholder="e.g. film, person, place"
							list="type-suggestions"
						/>
						<datalist id="type-suggestions">
							{#each knownTypeSlugs as slug (slug)}
								<option value={slug}></option>
							{/each}
						</datalist>
					</div>

					<div class="space-y-2">
						<Label for="description">Description</Label>
						<Textarea id="description" bind:value={description} />
					</div>

					<AttributesEditor bind:rows={attributeRows} />

					<div class="flex justify-end gap-2">
						<Button type="button" variant="outline" href={resolve('/nodes')}>Cancel</Button>
						<Button type="submit" disabled={submitting}>
							{submitting ? 'Creating…' : 'Create Node'}
						</Button>
					</div>
				</form>
			</Card.Content>
		</Card.Root>
	</div>
</main>
