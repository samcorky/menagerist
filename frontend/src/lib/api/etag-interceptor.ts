import { client } from './generated/client.gen';
import { getEtag, setEtag, clearEtag } from './etagStore';

const cacheKey = (url: string): string => {
	const parsed = new URL(url, 'http://x');
	return parsed.pathname + parsed.search;
};

client.interceptors.request.use((request) => {
	const key = cacheKey(request.url);
	const rec = getEtag(key);
	if (!rec) return request;

	const headers = new Headers(request.headers);
	if (request.method === 'GET' || request.method === 'HEAD') {
		if (rec.etag) headers.set('If-None-Match', rec.etag);
		if (rec.lastModified) headers.set('If-Modified-Since', rec.lastModified);
	} else if (
		request.method === 'PATCH' ||
		request.method === 'PUT' ||
		request.method === 'DELETE'
	) {
		if (rec.etag) headers.set('If-Match', rec.etag);
	}
	return new Request(request, { headers });
});

client.interceptors.response.use(async (response, request) => {
	const key = cacheKey(request.url);

	if (response.status === 200) {
		const contentType = response.headers.get('Content-Type') ?? '';
		let data: unknown;
		if (contentType.includes('application/json')) {
			try {
				data = await response.clone().json();
			} catch {
				// non-JSON body — store headers only
			}
		}
		setEtag(key, {
			etag: response.headers.get('ETag') ?? undefined,
			lastModified: response.headers.get('Last-Modified') ?? undefined,
			data
		});
		return response;
	}

	if (response.status === 304) {
		const rec = getEtag(key);
		if (rec?.data !== undefined) {
			const headers = new Headers(response.headers);
			headers.set('Content-Type', 'application/json');
			if (rec.etag) headers.set('ETag', rec.etag);
			if (rec.lastModified) headers.set('Last-Modified', rec.lastModified);
			return new Response(JSON.stringify(rec.data), { status: 200, headers });
		}
		return response;
	}

	if (response.status === 412) {
		clearEtag(key);
		return response;
	}

	return response;
});

export default {};
