<script lang="ts">
	import type { EditorField } from '$lib/schema-types';
	import ConstraintInputs from './ConstraintInputs.svelte';
	import { readTextConfig } from './constraints';

	let {
		field,
		onChange
	}: {
		field: EditorField;
		onChange: (f: EditorField) => void;
	} = $props();

	// Only the initial state decides whether the section starts open.
	const initiallyOpen = (() => {
		const c = readTextConfig(field);
		return Boolean(c.startsWith || c.endsWith || c.custom);
	})();
</script>

<details open={initiallyOpen} class="mt-1.5 ml-4 border-l border-input pl-3">
	<summary class="cursor-pointer text-xs text-muted-foreground select-none hover:text-foreground">
		Validation (optional)
	</summary>
	<div class="mt-1.5 space-y-1.5">
		<ConstraintInputs
			config={field.config}
			idPrefix="text-{field.key}"
			onChange={(config) => onChange({ ...field, config })}
		/>
	</div>
</details>
