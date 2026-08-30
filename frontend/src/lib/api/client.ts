import { client } from './generated/client.gen';

// Register ETag interceptor (side-effect). The interceptor attaches If-None-Match/If-Modified-Since
// on GETs, If-Match on mutations, caches ETag/Last-Modified and maps 304 -> cached body when possible.
import './etag-interceptor';

// Default baseUrl: use relative in browser, fallback to http://localhost for Node tests
const defaultBase = typeof window !== 'undefined' ? '' : 'http://localhost';
client.setConfig({ baseUrl: defaultBase });

export * from './generated';
