<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { captureController } from '$lib/capture.svelte.js';

	$effect(() => {
		captureController.show();
		void goto(resolve('/nodes'));
	});
</script>
