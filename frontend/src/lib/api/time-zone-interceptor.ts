import { resolvedZone } from '$lib/format-date';
import { client } from './generated/client.gen';

// The server works out "today" for relative dates (smart collections, "the last 30 days") in
// this zone: the person's chosen one, or the browser's.
client.interceptors.request.use((request) => {
	request.headers.set('Time-Zone', resolvedZone());
	return request;
});

export default {};
