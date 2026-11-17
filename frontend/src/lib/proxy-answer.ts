/**
 * Telling the app's own answers from a reverse proxy standing in for it.
 *
 * While a deployment swaps the container, a proxy such as Traefik has no backend to send a request
 * to and answers itself: a bare `404 page not found`, or a 502, 503 or 504. Menagerist never
 * answers like that: its errors are always RFC 9457 problem JSON, and every page path gets the
 * app shell. So a gateway-style status without problem JSON means the server cannot be reached,
 * and is treated exactly like a lost connection, never as "that does not exist".
 */

const GATEWAY_STATUSES = new Set([404, 502, 503, 504]);

/** Whether `response` came from something in front of the app rather than the app itself. */
export function answeredByProxy(response: Pick<Response, 'status' | 'headers'>): boolean {
	if (!GATEWAY_STATUSES.has(response.status)) return false;
	const type = response.headers.get('Content-Type') ?? '';
	return !type.toLowerCase().includes('application/problem+json');
}

/**
 * `fetch`, but a proxy's answer rejects with a `TypeError`, as a lost connection does, so the
 * client, the offline banner and every page handle it the same way.
 */
export async function proxyAwareFetch(
	input: RequestInfo | URL,
	init?: RequestInit
): Promise<Response> {
	const response = await fetch(input, init);
	if (answeredByProxy(response)) {
		throw new TypeError(`The server could not be reached (the proxy answered ${response.status}).`);
	}
	return response;
}
