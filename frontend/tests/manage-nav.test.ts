import { describe, expect, it } from 'vitest';
import {
	activeManageHref,
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
