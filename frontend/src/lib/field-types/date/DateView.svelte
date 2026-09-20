<script lang="ts">
	import type { JsonSchemaProperty } from '$lib/schema-types';

	let {
		value,
		prop: _prop
	}: {
		value: unknown;
		prop: JsonSchemaProperty;
	} = $props();

	let display = $derived.by((): string => {
		if (typeof value !== 'string' || value === '') return '—';
		try {
			return new Date(value + 'T00:00:00').toLocaleDateString(undefined, {
				year: 'numeric',
				month: 'long',
				day: 'numeric'
			});
		} catch {
			return String(value);
		}
	});
</script>

<span>{display}</span>
