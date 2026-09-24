import { client } from './generated/client.gen';

// Register the ETag interceptor.
import './etag-interceptor';

// Use relative URL in browser, fallback to localhost for Node tests.
const defaultBase = typeof window !== 'undefined' ? '' : 'http://localhost';
client.setConfig({ baseUrl: defaultBase });

export * from './generated';
