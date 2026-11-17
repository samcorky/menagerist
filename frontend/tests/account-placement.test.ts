import { describe, expect, it } from 'vitest';
import { accountMenuInTopBar } from '../src/lib/account-placement';

describe('accountMenuInTopBar', () => {
	it('leaves the account menu to the sidebar footer while the sidebar is on screen', () => {
		expect(accountMenuInTopBar({ sidebarShown: true, mode: 'expanded' })).toBe(false);
		expect(accountMenuInTopBar({ sidebarShown: true, mode: 'rail' })).toBe(false);
	});

	it('keeps it in the top bar when the sidebar is a hidden drawer', () => {
		expect(accountMenuInTopBar({ sidebarShown: true, mode: 'drawer' })).toBe(true);
	});

	it('keeps it in the top bar when there is no sidebar, so sign out stays reachable', () => {
		// For example while a password set by an administrator must be changed.
		expect(accountMenuInTopBar({ sidebarShown: false, mode: 'expanded' })).toBe(true);
	});
});
