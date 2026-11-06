import { offlineController } from '$lib/offline.svelte';
import { client } from './generated/client.gen';

client.interceptors.response.use((response) => {
	offlineController.reportReachable();
	return response;
});

// Runs when `fetch` rejects, before the client returns an error with no response.
client.interceptors.error.use((error) => {
	if (error instanceof TypeError) offlineController.reportUnreachable();
	return error;
});

export default {};
