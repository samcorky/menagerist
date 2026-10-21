import { test } from '@playwright/test';
import { COOKIES_BACKEND_PORT, ensureAdminSession } from './fixtures';

// The cookie specs run in three engines at once, so the administrator is made once here.
test('set up the cookie backend', async () => {
	await ensureAdminSession(`http://localhost:${COOKIES_BACKEND_PORT}`);
});
