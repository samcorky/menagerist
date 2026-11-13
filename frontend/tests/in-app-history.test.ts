import { beforeEach, describe, expect, it } from 'vitest';
import {
	canGoBackInApp,
	noteArrival,
	replaceNext,
	resetInAppHistory
} from '../src/lib/in-app-history';

const at = (pathname: string) => ({ url: { pathname } });

describe('in-app history depth', () => {
	beforeEach(resetInAppHistory);

	it('has nothing behind a page the app was opened on', () => {
		noteArrival({ type: 'enter', from: null, to: at('/items/1') });
		expect(canGoBackInApp()).toBe(false);
	});

	it('counts a link to another page, and a Back out of it', () => {
		noteArrival({ type: 'enter', from: null, to: at('/items') });
		noteArrival({ type: 'link', from: at('/items'), to: at('/items/1') });
		expect(canGoBackInApp()).toBe(true);
		noteArrival({ type: 'popstate', from: at('/items/1'), to: at('/items'), delta: -1 });
		expect(canGoBackInApp()).toBe(false);
	});

	it('ignores changes that stay on the same page, such as filters and sheets', () => {
		noteArrival({ type: 'enter', from: null, to: at('/items') });
		noteArrival({ type: 'goto', from: at('/items'), to: at('/items') });
		noteArrival({ type: 'popstate', from: at('/items'), to: at('/items'), delta: -1 });
		expect(canGoBackInApp()).toBe(false);
	});

	it('does not count a redirect that replaces the current entry', () => {
		noteArrival({ type: 'enter', from: null, to: at('/items/1') });
		replaceNext();
		noteArrival({ type: 'goto', from: at('/items/1'), to: at('/login') });
		expect(canGoBackInApp()).toBe(false);
	});

	it('never goes below nothing behind', () => {
		noteArrival({ type: 'enter', from: null, to: at('/a') });
		noteArrival({ type: 'popstate', from: at('/a'), to: at('/b'), delta: -3 });
		expect(canGoBackInApp()).toBe(false);
	});
});
