import { describe, expect, it } from 'vitest';
import { animatesNavigation } from '$lib/view-transition';

const at = (id: string | null, path = '/x') => ({ route: { id }, url: new URL(`http://x${path}`) });

describe('animatesNavigation', () => {
	it('animates moving between pages', () => {
		expect(
			animatesNavigation({ type: 'link', from: at('/collections'), to: at('/collections/[id]') })
		).toBe(true);
		expect(
			animatesNavigation({ type: 'goto', from: at('/items/[id]'), to: at('/collections') })
		).toBe(true);
	});

	it('animates following a link to another page of the same kind', () => {
		expect(
			animatesNavigation({
				type: 'link',
				from: at('/collections/[id]'),
				to: at('/collections/[id]')
			})
		).toBe(true);
	});

	it('does not animate a page rewriting its own address', () => {
		// The collection page replacing an id with its slug, or writing its filters
		expect(
			animatesNavigation({
				type: 'goto',
				from: at('/collections/[id]'),
				to: at('/collections/[id]')
			})
		).toBe(false);
		expect(animatesNavigation({ type: 'goto', from: at('/items'), to: at('/items') })).toBe(false);
	});

	it('does not animate Back or Forward within the same page', () => {
		expect(
			animatesNavigation({
				type: 'popstate',
				from: at('/items', '/items'),
				to: at('/items', '/items')
			})
		).toBe(false);
		expect(
			animatesNavigation({
				type: 'popstate',
				from: at('/collections/[id]', '/collections/a'),
				to: at('/collections/[id]', '/collections/a')
			})
		).toBe(false);
	});

	it('animates Back or Forward to another address', () => {
		expect(
			animatesNavigation({
				type: 'popstate',
				from: at('/collections/[id]', '/collections/a'),
				to: at('/collections/[id]', '/collections/b')
			})
		).toBe(true);
		expect(
			animatesNavigation({ type: 'popstate', from: at('/items', '/items'), to: at('/', '/') })
		).toBe(true);
	});

	it('animates when either end is unknown', () => {
		expect(animatesNavigation({ type: 'goto', from: null, to: at('/items') })).toBe(true);
		expect(animatesNavigation({ type: 'goto', from: at(null), to: at(null) })).toBe(true);
	});
});
