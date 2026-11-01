<script lang="ts">
	let {
		username,
		autocomplete = 'username'
	}: {
		username: string;
		/** Use `off` when the account is not the signed-in person's own, so it is never saved as theirs. */
		autocomplete?: 'username' | 'off';
	} = $props();
</script>

<!-- Names the account a password field belongs to, for password managers and assistive technology. -->
<input
	type="text"
	name="username"
	{autocomplete}
	value={username}
	readonly
	tabindex={-1}
	aria-label="Username"
	class="sr-only"
/>
