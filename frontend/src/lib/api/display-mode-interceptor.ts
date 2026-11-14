import { DISPLAY_MODE_HEADER, displayMode } from '$lib/display-mode.svelte';
import { client } from './generated/client.gen';

// The server records it when a session starts, to label the device "installed app".
client.interceptors.request.use((request) => {
	request.headers.set(DISPLAY_MODE_HEADER, displayMode.mode);
	return request;
});

export default {};
