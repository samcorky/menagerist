import { client } from './generated/client.gen';

// Register ETag interceptor (side-effect). The interceptor attaches If-None-Match/If-Modified-Since
// on GETs, If-Match on mutations, caches ETag/Last-Modified and maps 304 -> cached body when possible.
import './etag-interceptor';
// Register version-mismatch interceptor (side-effect). Reads App-Version from every response
// and signals the versionController if it differs from the build-time expected version.
import './version-header-interceptor';

// Default baseUrl: use relative in browser, fallback to http://localhost for Node tests
const defaultBase = typeof window !== 'undefined' ? '' : 'http://localhost';
client.setConfig({ baseUrl: defaultBase });

export * from './generated';
