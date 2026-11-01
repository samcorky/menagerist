<script lang="ts">
	import { lockPageScroll } from '$lib/scroll-lock';

	// Render this only while something modal is open: it freezes the page area behind it.
	$effect(() => lockPageScroll());
</script>
