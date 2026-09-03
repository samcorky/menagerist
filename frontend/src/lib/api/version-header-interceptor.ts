import { client } from './generated/client.gen';
import { versionController } from '$lib/version.svelte';

client.interceptors.response.use((response) => {
	const version = response.headers.get('App-Version');
	if (version) versionController.report(version);
	return response;
});

export default {};
