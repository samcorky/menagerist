import { client } from './generated/client.gen';

// Same-origin relative `/api/*` in both dev (Vite proxy, see vite.config.ts)
// and prod (nginx proxy) - the frontend never needs to know the backend's
// host/port.
client.setConfig({ baseUrl: '' });

export * from './generated';
