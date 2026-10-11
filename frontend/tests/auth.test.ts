import { describe, expect, it } from 'vitest';
import {
	authErrorMessage,
	ACCOUNT_DISABLED_MESSAGE,
	describeClaimed,
	displayNameProblem,
	isPasswordUnchanged,
	guardDecision,
	isUnsafeMethod,
	problemTitle,
	problemType,
	readCookie,
	safeNext,
	throttleMessage,
	type GuardInput
} from '../src/lib/auth';

describe('safeNext', () => {
	it.each([
		['/', '/'],
		['/items', '/items'],
		['/items/abc?x=1#top', '/items/abc?x=1#top'],
		['/settings/users', '/settings/users']
	])('keeps the same-origin path %s', (input, expected) => {
		expect(safeNext(input)).toBe(expected);
	});

	it.each([
		['https://evil.example/'],
		['http://evil.example'],
		['//evil.example'],
		['///evil.example'],
		['/\\evil.example'],
		['\\\\evil.example'],
		['javascript:alert(1)'],
		['data:text/html,x'],
		['%2F%2Fevil.example'],
		['/%2Fevil.example'],
		['/%5Cevil.example'],
		['/%252F%252Fevil.example'],
		['/\t/evil.example'],
		['/%09/evil.example'],
		['/%0d%0aSet-Cookie:x=1'],
		['/%E0%A4%A'],
		['items'],
		[' /items'],
		[''],
		['/login'],
		['/login?next=/items'],
		['/setup']
	])('falls back to / for %j', (input) => {
		expect(safeNext(input)).toBe('/');
	});

	it('falls back to / for null and undefined', () => {
		expect(safeNext(null)).toBe('/');
		expect(safeNext(undefined)).toBe('/');
	});
});

describe('guardDecision', () => {
	const base: GuardInput = {
		pathname: '/items',
		search: '',
		setupRequired: false,
		signedIn: true,
		passwordExpired: false
	};
	const redirect = (to: string) => ({ action: 'redirect', to });
	const allow = { action: 'allow' };

	it('sends everything to setup while setup is required', () => {
		const input = { ...base, setupRequired: true, signedIn: false };
		expect(guardDecision(input)).toEqual(redirect('/setup'));
		expect(guardDecision({ ...input, pathname: '/login' })).toEqual(redirect('/setup'));
		expect(guardDecision({ ...input, pathname: '/setup' })).toEqual(allow);
	});

	it('sends visitors without a session to sign in, remembering the page', () => {
		const input = { ...base, signedIn: false };
		expect(guardDecision({ ...input, pathname: '/items/1', search: '?q=a b' })).toEqual(
			redirect('/login?next=' + encodeURIComponent('/items/1?q=a b'))
		);
		expect(guardDecision({ ...input, pathname: '/login' })).toEqual(allow);
		expect(guardDecision({ ...input, pathname: '/' })).toEqual(redirect('/login'));
	});

	it('keeps the query string and hash of a deep link in next', () => {
		const input = { ...base, signedIn: false };
		const decision = guardDecision({
			...input,
			pathname: '/collections/abc',
			search: '?tab=items&q=a%26b',
			hash: '#top'
		});
		expect(decision).toEqual(
			redirect('/login?next=' + encodeURIComponent('/collections/abc?tab=items&q=a%26b#top'))
		);
		const to = (decision as { to: string }).to;
		const next = new URLSearchParams(to.split('?')[1]).get('next');
		expect(safeNext(next)).toBe('/collections/abc?tab=items&q=a%26b#top');
	});

	it('does not touch a signed-in deep link with a query string', () => {
		expect(guardDecision({ ...base, pathname: '/items', search: '?q=x&type=film' })).toEqual(allow);
		expect(
			guardDecision({ ...base, pathname: '/collections/abc', search: '?tab=items', hash: '#a' })
		).toEqual(allow);
	});

	it('returns a signed-in visitor on /login to next with its query string', () => {
		expect(
			guardDecision({
				...base,
				pathname: '/login',
				search: '?next=' + encodeURIComponent('/items?q=x#top')
			})
		).toEqual(redirect('/items?q=x#top'));
	});

	it('does not remember the page after an explicit sign-out', () => {
		expect(guardDecision({ ...base, signedIn: false, rememberPath: false })).toEqual(
			redirect('/login')
		);
	});

	it('sends /setup back to sign in once setup is done', () => {
		expect(guardDecision({ ...base, signedIn: false, pathname: '/setup' })).toEqual(
			redirect('/login')
		);
	});

	it('sends signed-in users away from the public pages', () => {
		expect(guardDecision({ ...base, pathname: '/setup' })).toEqual(redirect('/'));
		expect(guardDecision({ ...base, pathname: '/login' })).toEqual(redirect('/'));
		expect(guardDecision({ ...base, pathname: '/login', search: '?next=%2Fitems' })).toEqual(
			redirect('/items')
		);
		expect(
			guardDecision({ ...base, pathname: '/login', search: '?next=https%3A%2F%2Fevil.example' })
		).toEqual(redirect('/'));
	});

	it('confines an expired password to the account page', () => {
		const input = { ...base, passwordExpired: true };
		expect(guardDecision(input)).toEqual(redirect('/settings/account'));
		expect(guardDecision({ ...input, pathname: '/login' })).toEqual(redirect('/settings/account'));
		expect(guardDecision({ ...input, pathname: '/settings/account' })).toEqual(allow);
		expect(guardDecision({ ...input, pathname: '/settings/account/' })).toEqual(allow);
	});

	it('lets a signed-in user see ordinary pages', () => {
		expect(guardDecision(base)).toEqual(allow);
		expect(guardDecision({ ...base, pathname: '/settings/users' })).toEqual(allow);
	});
});

describe('cookies and methods', () => {
	it('reads a named cookie', () => {
		expect(readCookie('a=1; menagerist_csrf=tok%2Fen; b=2', 'menagerist_csrf')).toBe('tok/en');
		expect(readCookie('a=1', 'menagerist_csrf')).toBeNull();
		expect(readCookie('', 'x')).toBeNull();
	});

	it('flags only unsafe methods', () => {
		for (const m of ['POST', 'put', 'PATCH', 'DELETE']) expect(isUnsafeMethod(m)).toBe(true);
		for (const m of ['GET', 'HEAD', 'OPTIONS']) expect(isUnsafeMethod(m)).toBe(false);
	});
});

describe('messages', () => {
	it('extracts the problem type', () => {
		expect(problemType({ type: 'password_expired' })).toBe('password_expired');
		expect(problemType({})).toBeNull();
		expect(problemType(null)).toBeNull();
	});

	it('words the throttle message in minutes', () => {
		expect(throttleMessage(30)).toBe('Too many attempts. Try again in 1 minute.');
		expect(throttleMessage(61)).toBe('Too many attempts. Try again in 2 minutes.');
		expect(throttleMessage(900)).toBe('Too many attempts. Try again in 15 minutes.');
		expect(throttleMessage(null)).toContain('Wait a little while');
	});

	it('uses the Retry-After header for a 429', () => {
		const response = new Response(null, { status: 429, headers: { 'Retry-After': '600' } });
		expect(authErrorMessage({ error: {}, response })).toBe(
			'Too many attempts. Try again in 10 minutes.'
		);
	});

	it('uses the server detail otherwise, and handles offline and server errors', () => {
		const response = new Response(null, { status: 401 });
		expect(authErrorMessage({ error: { detail: 'Wrong username or password.' }, response })).toBe(
			'Wrong username or password.'
		);
		expect(authErrorMessage({ error: undefined, response: null })).toContain('offline');
		expect(
			authErrorMessage({ error: {}, response: new Response(null, { status: 500 }) })
		).toContain('Something went wrong');
	});

	it('describes claimed data and skips empty kinds', () => {
		expect(describeClaimed({ items: 3, connections: 1, collections: 0, files: 2 })).toEqual([
			'3 items',
			'1 connection',
			'2 files'
		]);
		expect(describeClaimed({ items: 0 })).toEqual([]);
	});
});

describe('identity errors', () => {
	it('shows the fixed disabled-account message for a 403 account_disabled', () => {
		const response = new Response(null, { status: 403 });
		expect(authErrorMessage({ error: { type: 'account_disabled', detail: 'x' }, response })).toBe(
			ACCOUNT_DISABLED_MESSAGE
		);
		// Other 403s keep the server detail.
		expect(authErrorMessage({ error: { type: 'about:blank', detail: 'No.' }, response })).toBe(
			'No.'
		);
	});

	it('reads the problem title and spots an unchanged password', () => {
		expect(problemTitle({ title: 'PasswordUnchangedError' })).toBe('PasswordUnchangedError');
		expect(problemTitle({})).toBeNull();
		expect(isPasswordUnchanged({ title: 'PasswordUnchangedError' })).toBe(true);
		expect(isPasswordUnchanged({ title: 'CurrentPasswordIncorrectError' })).toBe(false);
	});

	it('validates display names after trimming', () => {
		expect(displayNameProblem('   ')).not.toBeNull();
		expect(displayNameProblem('Sam')).toBeNull();
		expect(displayNameProblem('a'.repeat(120))).toBeNull();
		expect(displayNameProblem('a'.repeat(121))).not.toBeNull();
	});
});
