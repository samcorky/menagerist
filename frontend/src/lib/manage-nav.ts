import type { Component } from 'svelte';
import {
	Activity,
	ArrowLeftRight,
	Archive,
	Bookmark,
	CalendarClock,
	Compass,
	House,
	Laptop,
	LayoutGrid,
	Library,
	Shield,
	SlidersHorizontal,
	Sparkles,
	Tag,
	Trash2,
	UserRound,
	Users
} from '@lucide/svelte';
import type { Permission } from '$lib/auth';

/** Whether the signed-in account holds a permission (`auth.can`). */
export type ManagePermissionCheck = (permission: Permission) => boolean;

export type ManageItem = {
	href: string;
	label: string;
	icon: Component;
	/** Shown only to accounts that hold this permission, like the Administration hub's cards. */
	permission?: Permission;
	/** The tile copy on a hub page. Sidebar rows show the label alone. */
	description?: string;
	/** Which hub page lists this entry as a tile. Sidebar-only entries leave it unset. */
	hub?: ManageHub;
};

/** The two hub pages that list entries as tiles: /settings and /admin. */
export type ManageHub = 'settings' | 'admin';

export type ManageGroup = { label: string; items: ManageItem[] };

/** The everyday destinations, shown above the groups in the app sidebar. */
export const mainDestinations: ManageItem[] = [
	{ href: '/', label: 'Home', icon: House },
	{ href: '/items', label: 'Items', icon: LayoutGrid },
	{ href: '/collections', label: 'Collections', icon: Library },
	{ href: '/explore', label: 'Explore', icon: Compass }
];

const LIBRARY: ManageItem[] = [
	{
		href: '/settings/item-types',
		label: 'Item types',
		icon: Tag,
		hub: 'settings',
		description: 'Organise your items with types like "Film", "Person", or "Event".'
	},
	{
		href: '/settings/relationships',
		label: 'Relationship types',
		icon: ArrowLeftRight,
		hub: 'settings',
		description: 'Define how items connect - "Directed by", "Signed by", "Part of".'
	},
	{
		href: '/settings/saved-fields',
		label: 'Saved fields',
		icon: Bookmark,
		hub: 'settings',
		description: 'Reuse a field or a list of choices across item types.'
	},
	{
		href: '/settings/examples',
		label: 'Examples',
		icon: Sparkles,
		hub: 'settings',
		description: 'Explore Menagerist with ready-made example items.'
	},
	{
		href: '/recently-deleted',
		label: 'Recently deleted',
		icon: Trash2,
		hub: 'settings',
		description: 'Restore items and collections you deleted, or delete them for good.'
	}
];

const ACCOUNT: ManageItem[] = [
	{
		href: '/settings/account',
		label: 'Account',
		icon: UserRound,
		hub: 'settings',
		description: 'Change your password.'
	}
];

const SYSTEM: ManageItem[] = [
	{
		href: '/status',
		label: 'Status',
		icon: Activity,
		hub: 'settings',
		description: 'Health checks, database connectivity, and build info.'
	},
	{
		href: '/admin/users',
		label: 'Users',
		icon: Users,
		permission: 'identity:user:list',
		hub: 'admin',
		description: 'Add people, change roles and reset passwords.'
	},
	{
		href: '/admin/devices',
		label: 'Devices',
		icon: Laptop,
		permission: 'identity:session:list',
		hub: 'admin',
		description: "See everyone's active devices and sign them out."
	},
	{
		href: '/admin/backups',
		label: 'Backups',
		icon: Archive,
		permission: 'backup:archive:read',
		hub: 'admin',
		description: 'Create, download and check complete instance backups.'
	},
	{
		href: '/admin/scheduled-tasks',
		label: 'Scheduled tasks',
		icon: CalendarClock,
		permission: 'scheduling:job:read',
		hub: 'admin',
		description: 'See what runs in the background and start a task now.'
	},
	{
		href: '/admin/settings',
		label: 'Admin settings',
		icon: SlidersHorizontal,
		permission: 'settings:instance:read',
		hub: 'admin',
		description: 'Change schedules and how long things are kept.'
	}
];

/** The sidebar's sections, with admin entries left out for accounts without their permission. */
export function manageGroups(can: ManagePermissionCheck): ManageGroup[] {
	const visible = (items: ManageItem[]) =>
		items.filter((item) => !item.permission || can(item.permission));
	return [
		{ label: 'Library', items: LIBRARY },
		{ label: 'Account', items: ACCOUNT },
		{ label: 'System', items: visible(SYSTEM) }
	];
}

/** The hub pages themselves, which list the entries below them rather than being one. */
const HUB_HREFS: Record<ManageHub, string> = { settings: '/settings', admin: '/admin' };

/** The single tile on /settings standing in for the whole Administration hub. */
const ADMIN_TILE: ManageItem = {
	href: '/admin',
	label: 'Administration',
	icon: Shield,
	description: 'Manage users, devices, backups, scheduled tasks and settings.'
};

/** Whether the account can reach any page on the Administration hub. */
export function canSeeAdmin(can: ManagePermissionCheck): boolean {
	return SYSTEM.some((item) => item.permission !== undefined && can(item.permission));
}

/**
 * A hub page's tiles, in sidebar order, left out for accounts without their permission. The
 * Administration hub is one tile on /settings rather than its five pages being repeated there.
 */
export function hubTiles(hub: ManageHub, can: ManagePermissionCheck): ManageItem[] {
	const tiles = manageGroups(can)
		.flatMap((group) => group.items)
		.filter((item) => item.hub === hub);
	return hub === 'settings' && canSeeAdmin(can) ? [...tiles, ADMIN_TILE] : tiles;
}

/** Whether a path belongs to the settings and administration area that gets the sidebar. */
export function isManageRoute(pathname: string): boolean {
	const hrefs = [
		...Object.values(HUB_HREFS),
		...[LIBRARY, ACCOUNT, SYSTEM].flat().map((i) => i.href)
	];
	return hrefs.some((href) => pathname === href || pathname.startsWith(`${href}/`));
}

/** The sidebar entry for the current path (also for pages below it); none on the hub pages. */
export function activeManageHref(pathname: string, can: ManagePermissionCheck): string | undefined {
	const sections = manageGroups(can).flatMap((group) => group.items);
	return [...mainDestinations, ...sections].find((item) =>
		item.href === '/'
			? pathname === '/'
			: pathname === item.href || pathname.startsWith(`${item.href}/`)
	)?.href;
}
