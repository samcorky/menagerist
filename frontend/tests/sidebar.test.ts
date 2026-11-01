import { afterEach, describe, expect, it, vi } from 'vitest';
import { SidebarController, defaultMode } from '$lib/sidebar.svelte';

function memoryStorage(initial: Record<string, string> = {}) {
	const data = new Map(Object.entries(initial));
	return {
		data,
		getItem: (key: string) => data.get(key) ?? null,
		setItem: (key: string, value: string) => void data.set(key, value)
	};
}

afterEach(() => vi.unstubAllGlobals());

describe('defaultMode', () => {
	it.each([
		[2048, 'expanded'],
		[1280, 'expanded'],
		[1279, 'rail'],
		[768, 'rail'],
		[767, 'drawer'],
		[360, 'drawer']
	])('picks the right mode at %ipx', (width, mode) => {
		expect(defaultMode(width)).toBe(mode);
	});
});

describe('SidebarController', () => {
	it('follows the width when nothing is remembered', () => {
		vi.stubGlobal('localStorage', memoryStorage());
		const sidebar = new SidebarController(2048);
		expect(sidebar.mode).toBe('expanded');
		sidebar.setWidth(1000);
		expect(sidebar.mode).toBe('rail');
		sidebar.setWidth(400);
		expect(sidebar.mode).toBe('drawer');
	});

	it('uses a remembered choice on wide screens but never lets it hide the drawer', () => {
		vi.stubGlobal('localStorage', memoryStorage({ 'menagerist:sidebar:expanded': '0' }));
		const sidebar = new SidebarController(2048);
		expect(sidebar.mode).toBe('rail');
		sidebar.setWidth(500);
		expect(sidebar.mode).toBe('drawer');
	});

	it('toggles between expanded and rail and remembers the choice', () => {
		const storage = memoryStorage();
		vi.stubGlobal('localStorage', storage);
		const sidebar = new SidebarController(2048);
		sidebar.toggle();
		expect(sidebar.mode).toBe('rail');
		expect(storage.data.get('menagerist:sidebar:expanded')).toBe('0');
		sidebar.toggle();
		expect(sidebar.mode).toBe('expanded');
		expect(storage.data.get('menagerist:sidebar:expanded')).toBe('1');
	});

	it('opens and closes the drawer on narrow screens', () => {
		vi.stubGlobal('localStorage', memoryStorage());
		const sidebar = new SidebarController(400);
		expect(sidebar.drawerOpen).toBe(false);
		sidebar.toggle();
		expect(sidebar.drawerOpen).toBe(true);
		sidebar.closeDrawer();
		expect(sidebar.drawerOpen).toBe(false);
	});

	it('closes the drawer when the screen grows wide enough for a sidebar', () => {
		vi.stubGlobal('localStorage', memoryStorage());
		const sidebar = new SidebarController(400);
		sidebar.toggle();
		sidebar.setWidth(1000);
		expect(sidebar.drawerOpen).toBe(false);
		expect(sidebar.mode).toBe('rail');
	});

	it('works when storage throws', () => {
		vi.stubGlobal('localStorage', {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		});
		const sidebar = new SidebarController(2048);
		expect(() => sidebar.toggle()).not.toThrow();
		expect(sidebar.mode).toBe('rail');
	});
});
