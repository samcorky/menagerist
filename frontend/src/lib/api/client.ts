import { client } from './generated/client.gen';

// Register ETag and version-mismatch interceptors.
import './etag-interceptor';
import './version-header-interceptor';

// Use relative URL in browser, fallback to localhost for Node tests.
const defaultBase = typeof window !== 'undefined' ? '' : 'http://localhost';
client.setConfig({ baseUrl: defaultBase });

export * from './generated';
