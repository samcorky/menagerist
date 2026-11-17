import { client } from './generated/client.gen';
import { proxyAwareFetch } from '$lib/proxy-answer';

// Register the ETag interceptor.
import './etag-interceptor';
// 401 / password-expired handling.
import './auth-interceptor';
// Tracks whether the server can be reached.
import './offline-interceptor';
// Says whether the app runs installed or in a browser tab.
import './display-mode-interceptor';

// Use relative URL in browser, fallback to localhost for Node tests.
const defaultBase = typeof window !== 'undefined' ? '' : 'http://localhost';
// A proxy answering for a server that is not there (mid-deployment) counts as unreachable.
client.setConfig({ baseUrl: defaultBase, fetch: proxyAwareFetch });

export * from './generated';
export { client };
