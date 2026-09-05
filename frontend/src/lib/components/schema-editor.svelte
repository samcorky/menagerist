<script lang="ts" module>
	export type SchemaField = {
		key: string;
		label: string;
		type: 'text' | 'number' | 'boolean' | 'date' | 'select' | 'richtext';
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
	import { slugify } from '$lib/utils.js';

	let { schema = $bindable<Schema | null>(null) }: { schema?: Schema | null } = $props();

	let fields = $state<SchemaField[]>(schema?.fields ?? []);

	$effect(() => {
		schema = { fields };
	});

	function addField() {
		fields = [...fields, { key: '', label: '', type: 'text', required: false }];
	}

	function removeField(index: number) {
		fields = fields.filter((_, i) => i !== index);
	}

	function handleLabelChange(index: number, value: string) {
		fields = fields.map((f, i) => {
			if (i !== index) return f;
			// Lock the key once set — only derive on first non-empty label
			return { ...f, label: value, key: f.key || slugify(value) };
		});
	}
</script>

<div class="space-y-3">
	<Label>Fields</Label>

	{#each fields as field, i (i)}
		<div class="flex flex-wrap items-center gap-2">
			<Input
				value={field.label}
				placeholder="Label"
				class="w-40"
				aria-label="Field label"
				oninput={(e) => handleLabelChange(i, (e.target as HTMLInputElement).value)}
			/>
			<select
				bind:value={field.type}
				class="h-9 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
				aria-label="Field kind"
			>
				<option value="text">Text</option>
				<option value="number">Number</option>
				<option value="boolean">Yes/No</option>
				<option value="date">Date</option>
				<option value="select">Choice</option>
				<option value="richtext">Long text</option>
			</select>
			<label class="flex items-center gap-1.5 text-sm">
				<input
					type="checkbox"
					bind:checked={field.required}
					class="h-4 w-4 rounded border-input accent-primary"
				/>
				Required
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
