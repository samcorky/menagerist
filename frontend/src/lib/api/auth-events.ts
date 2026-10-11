import { problemType } from '$lib/auth';

export interface AuthEventHandlers {
	onUnauthenticated: () => void;
	onSetupRequired: () => void;
	onPasswordExpired: () => void;
}

// Calls that report their own failure; the controller or the page handles them.
const SELF_HANDLED = [
	'/api/v1/auth/login',
	'/api/v1/auth/setup',
	'/api/v1/auth/status',
	'/api/v1/auth/me',
	'/api/v1/auth/me/permissions',
	'/api/v1/auth/logout'
];

let handlers: AuthEventHandlers | null = null;
let unauthenticatedHandled = false;

export function registerAuthHandlers(next: AuthEventHandlers | null): void {
	handlers = next;
	unauthenticatedHandled = false;
}

/** Allow the next 401 to be handled again, e.g. after a fresh sign-in. */
export function resetAuthEvents(): void {
	unauthenticatedHandled = false;
}

/** React to a 401 or password-expired 403 once, however many calls fail together. */
export async function handleAuthResponse(response: Response, requestUrl: string): Promise<void> {
	if (!handlers || (response.status !== 401 && response.status !== 403)) return;
	const path = new URL(requestUrl, 'http://x').pathname;

	if (response.status === 401) {
		if (unauthenticatedHandled || SELF_HANDLED.includes(path)) return;
		unauthenticatedHandled = true;
		let type: string | null = null;
		try {
			type = problemType(await response.clone().json());
		} catch {
			// not a problem body - treat as a plain sign-out
		}
		if (type === 'setup_required') handlers.onSetupRequired();
		else handlers.onUnauthenticated();
		return;
	}

	try {
		if (problemType(await response.clone().json()) === 'password_expired') {
			handlers.onPasswordExpired();
		}
	} catch {
		// not a problem body
	}
}
