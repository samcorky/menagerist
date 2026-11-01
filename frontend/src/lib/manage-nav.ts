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
};

export type ManageGroup = { label: string; items: ManageItem[] };

/** The everyday destinations, shown above the groups in the app sidebar. */
export const mainDestinations: ManageItem[] = [
	{ href: '/', label: 'Home', icon: House },
	{ href: '/items', label: 'Items', icon: LayoutGrid },
	{ href: '/collections', label: 'Collections', icon: Library },
	{ href: '/explore', label: 'Explore', icon: Compass }
];

const LIBRARY: ManageItem[] = [
	{ href: '/settings/item-types', label: 'Item types', icon: Tag },
	{ href: '/settings/relationships', label: 'Relationship types', icon: ArrowLeftRight },
	{ href: '/settings/saved-fields', label: 'Saved fields', icon: Bookmark },
	{ href: '/settings/examples', label: 'Examples', icon: Sparkles },
	{ href: '/recently-deleted', label: 'Recently deleted', icon: Trash2 }
];

const ACCOUNT: ManageItem[] = [{ href: '/settings/account', label: 'Account', icon: UserRound }];

const SYSTEM: ManageItem[] = [
	{ href: '/status', label: 'Status', icon: Activity },
	{ href: '/admin/users', label: 'Users', icon: Users, permission: 'identity:user:list' },
	{ href: '/admin/devices', label: 'Devices', icon: Laptop, permission: 'identity:session:list' },
	{ href: '/admin/backups', label: 'Backups', icon: Archive, permission: 'backup:archive:read' },
	{
		href: '/admin/scheduled-tasks',
		label: 'Scheduled tasks',
		icon: CalendarClock,
		permission: 'scheduling:job:read'
	},
	{
		href: '/admin/settings',
		label: 'Admin settings',
		icon: SlidersHorizontal,
		permission: 'settings:instance:read'
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

/** Whether a path belongs to the settings and administration area that gets the sidebar. */
export function isManageRoute(pathname: string): boolean {
	return (
		/^\/(settings|admin)(\/|$)/.test(pathname) ||
		/^\/(recently-deleted|status)(\/|$)/.test(pathname)
	);
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
