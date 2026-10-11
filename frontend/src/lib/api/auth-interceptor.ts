import { client } from './generated/client.gen';
import { csrfToken, CSRF_HEADER, isUnsafeMethod } from '$lib/auth';
import { carryStamp } from './etagStore';
import { handleAuthResponse } from './auth-events';

// Unsafe requests carry the CSRF cookie's value back as a header.
client.interceptors.request.use((request) => {
	if (!isUnsafeMethod(request.method)) return request;
	const token = csrfToken();
	if (!token) return request;
	const headers = new Headers(request.headers);
	headers.set(CSRF_HEADER, token);
	return carryStamp(request, new Request(request, { headers }));
});

client.interceptors.response.use(async (response, request) => {
	await handleAuthResponse(response, request.url);
	return response;
});

export default {};
