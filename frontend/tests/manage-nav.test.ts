import { describe, expect, it } from 'vitest';
import {
	activeManageHref,
	canSeeAdmin,
	hubTiles,
	mainDestinations,
	isManageRoute,
	manageGroups,
	type ManagePermissionCheck
} from '$lib/manage-nav';

const none: ManagePermissionCheck = () => false;
const all: ManagePermissionCheck = () => true;
const hrefs = (can: ManagePermissionCheck) =>
	manageGroups(can).flatMap((group) => group.items.map((item) => item.href));

describe('isManageRoute', () => {
	it.each([
		'/settings',
		'/settings/account',
		'/settings/item-types',
		'/admin',
		'/admin/users',
		'/recently-deleted',
		'/status'
	])('is true for %s', (path) => expect(isManageRoute(path)).toBe(true));

	it.each(['/', '/items', '/items/abc', '/collections', '/login', '/settingsfoo'])(
		'is false for %s',
		(path) => expect(isManageRoute(path)).toBe(false)
	);

	it('covers every registered entry, so a new one needs no second list', () => {
		const every = manageGroups(() => true).flatMap((group) => group.items);
		for (const item of every) expect(isManageRoute(item.href)).toBe(true);
	});

	// The mobile tab bar highlights from this, and these two sit outside /settings.
	it.each(['/status', '/recently-deleted'])('is true for %s, outside /settings', (path) =>
		expect(isManageRoute(path)).toBe(true)
	);
});

describe('hubTiles', () => {
	const titles = (hub: 'settings' | 'admin', can: ManagePermissionCheck) =>
		hubTiles(hub, can).map((tile) => tile.label);

	it('lists the settings hub in sidebar order, with Administration last', () => {
		expect(titles('settings', all)).toEqual([
			'Item types',
			'Relationship types',
			'Saved fields',
			'Examples',
			'Recently deleted',
			'Account',
			'Status',
			'Administration'
		]);
	});

	it('leaves Administration off the settings hub without any admin permission', () => {
		expect(titles('settings', none)).not.toContain('Administration');
	});

	it('lists only the admin pages the account can reach', () => {
		expect(titles('admin', all)).toEqual([
			'Users',
			'Devices',
			'Backups',
			'Scheduled tasks',
			'Admin settings'
		]);
		expect(titles('admin', none)).toEqual([]);
		expect(titles('admin', (p) => p === 'backup:archive:read')).toEqual(['Backups']);
	});

	it('gives every tile the description its card needs', () => {
		for (const tile of [...hubTiles('settings', all), ...hubTiles('admin', all)]) {
			expect(tile.description).toBeTruthy();
		}
	});

	it('never shows a hub page as a tile on itself', () => {
		expect(hubTiles('settings', all).map((t) => t.href)).not.toContain('/settings');
		expect(hubTiles('admin', all).map((t) => t.href)).not.toContain('/admin');
	});
});

describe('canSeeAdmin', () => {
	it('is true with any one admin permission and false with none', () => {
		expect(canSeeAdmin(all)).toBe(true);
		expect(canSeeAdmin(none)).toBe(false);
		expect(canSeeAdmin((p) => p === 'scheduling:job:read')).toBe(true);
	});

	// A permission no admin entry asks for, so holding it alone opens nothing.
	it('checks only the permissions the admin entries actually name', () => {
		expect(canSeeAdmin((p) => p === 'identity:user:create')).toBe(false);
	});
});

describe('manageGroups', () => {
	it('groups the always-available sections as Library, Account and System', () => {
		const groups = manageGroups(none);
		expect(groups.map((g) => g.label)).toEqual(['Library', 'Account', 'System']);
		expect(hrefs(none)).toEqual([
			'/settings/item-types',
			'/settings/relationships',
			'/settings/saved-fields',
			'/settings/examples',
			'/recently-deleted',
			'/settings/account',
			'/status'
		]);
	});

	it('shows admin sections only to accounts holding their permission', () => {
		expect(hrefs(none).some((href) => href.startsWith('/admin'))).toBe(false);
		expect(hrefs(all).filter((href) => href.startsWith('/admin'))).toEqual([
			'/admin/users',
			'/admin/devices',
			'/admin/backups',
			'/admin/scheduled-tasks',
			'/admin/settings'
		]);
	});

	it('checks each admin section against its own permission', () => {
		const onlyBackups: ManagePermissionCheck = (p) => p === 'backup:archive:read';
		expect(hrefs(onlyBackups).filter((href) => href.startsWith('/admin'))).toEqual([
			'/admin/backups'
		]);
	});
});

describe('activeManageHref', () => {
	it('matches a section by its path', () => {
		expect(activeManageHref('/admin/users', all)).toBe('/admin/users');
	});

	it('ignores a trailing slash and deeper paths', () => {
		expect(activeManageHref('/admin/users/', all)).toBe('/admin/users');
		expect(activeManageHref('/settings/item-types/abc', all)).toBe('/settings/item-types');
	});

	it('is undefined on the hub pages and for sections the account cannot see', () => {
		expect(activeManageHref('/settings', all)).toBeUndefined();
		expect(activeManageHref('/admin', all)).toBeUndefined();
		expect(activeManageHref('/admin/users', none)).toBeUndefined();
	});
});

describe('main destinations', () => {
	it('lists Home, Items, Collections and Explore in that order', () => {
		expect(mainDestinations.map((item) => [item.label, item.href])).toEqual([
			['Home', '/'],
			['Items', '/items'],
			['Collections', '/collections'],
			['Explore', '/explore']
		]);
	});

	it('matches Home only on the home page, and the others by path prefix', () => {
		expect(activeManageHref('/', all)).toBe('/');
		expect(activeManageHref('/items/abc', all)).toBe('/items');
		expect(activeManageHref('/items/new', all)).toBe('/items');
		expect(activeManageHref('/collections/some-slug', all)).toBe('/collections');
		expect(activeManageHref('/explore', all)).toBe('/explore');
		expect(activeManageHref('/login', all)).toBeUndefined();
	});
});
