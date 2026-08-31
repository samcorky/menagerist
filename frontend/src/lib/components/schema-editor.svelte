<script lang="ts" module>
	export type SchemaField = {
		key: string;
		label: string;
		type: 'text' | 'number' | 'boolean' | 'date' | 'select';
		required: boolean;
		options?: string[];
	};

	export type Schema = { fields: SchemaField[] };
</script>

<script lang="ts">
	import { Plus, X } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';

	let { schema = $bindable<Schema | null>(null) }: { schema?: Schema | null } = $props();

	// Initialise internally if null
	let fields = $state<SchemaField[]>(schema?.fields ?? []);

	// Keep schema in sync with internal fields
	$effect(() => {
		schema = { fields };
	});

	function addField() {
		fields = [...fields, { key: '', label: '', type: 'text', required: false }];
	}

	function removeField(index: number) {
		fields = fields.filter((_, i) => i !== index);
	}
</script>

<div class="space-y-3">
	<Label>Attribute Schema</Label>

	{#each fields as field, i (i)}
		<div class="flex flex-wrap items-center gap-2">
			<Input bind:value={field.key} placeholder="key" class="w-28" aria-label="Field key" />
			<Input bind:value={field.label} placeholder="Label" class="w-32" aria-label="Field label" />
			<select
				bind:value={field.type}
				class="h-9 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
				aria-label="Field type"
			>
				<option value="text">text</option>
				<option value="number">number</option>
				<option value="boolean">boolean</option>
				<option value="date">date</option>
				<option value="select">select</option>
			</select>
			<label class="flex items-center gap-1 text-sm">
				<input
					type="checkbox"
					bind:checked={field.required}
					class="h-4 w-4 rounded border-input accent-primary"
				/>
				Req
			</label>
			<Button
				type="button"
				variant="ghost"
				size="icon"
				onclick={() => removeField(i)}
				aria-label="Remove field"
			>
				<X class="size-4" />
			</Button>
		</div>
	{/each}

	<Button type="button" variant="outline" size="sm" onclick={addField}>
		<Plus class="size-4" />
		Add field
	</Button>
</div>
