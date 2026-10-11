import {
	changePassword as apiChangePassword,
	getAuthStatus,
	getCurrentUser,
	getMyPermissions,
	setupFirstAdmin,
	signIn as apiSignIn,
	signOut as apiSignOut,
	type UserResponse
} from '$lib/api/client';
import { registerAuthHandlers, resetAuthEvents } from '$lib/api/auth-events';
import { clearAllEtags } from '$lib/api/etagStore';
import { authErrorMessage, type Permission } from '$lib/auth';

export type AuthResult = { ok: true } | { ok: false; message: string };
export type SetupResult = { ok: true; claimed: Record<string, number> } | AuthResult;

type SessionOutcome = 'signed-in' | 'signed-out' | 'failed';

const OFFLINE = 'You appear to be offline. Check your connection and try again.';

/**
 * The signed-in account and what it may do. No password is ever kept here;
 * the session itself lives in an HttpOnly cookie the page cannot read.
 */
class AuthController {
	user = $state.raw<UserResponse | null>(null);
	permissions = $state.raw<ReadonlySet<Permission>>(new Set());
	setupRequired = $state(false);
	/** True once the first status check has finished. */
	ready = $state(false);
	/** True when the status check could not reach the server. */
	loadFailed = $state(false);
	/** Set by an explicit sign-out so the sign-in page does not ask to return here. */
	leftOnPurpose = $state(false);

	signedIn = $derived(this.user !== null);
	passwordExpired = $derived(this.user?.password_expired ?? false);
	isAdmin = $derived(this.user?.role === 'admin');

	constructor() {
		registerAuthHandlers({
			onUnauthenticated: () => this.clearSession(),
			onSetupRequired: () => {
				this.clearSession();
				this.setupRequired = true;
			},
			onPasswordExpired: () => {
				if (this.user && !this.user.password_expired) {
					this.user = { ...this.user, password_expired: true };
					this.permissions = new Set();
				}
			}
		});
	}

	/** Whether the signed-in account holds `permission`. */
	can(permission: Permission): boolean {
		return this.permissions.has(permission);
	}

	/** Check setup status and the current session; safe to call again to retry. */
	async init(): Promise<void> {
		this.loadFailed = false;
		try {
			const status = await getAuthStatus();
			if (status.error || !status.data) {
				this.loadFailed = true;
				return;
			}
			this.setupRequired = status.data.setup_required;
			if (!this.setupRequired && (await this.loadSession()) === 'failed') {
				this.loadFailed = true;
				return;
			}
			this.ready = true;
		} catch {
			this.loadFailed = true;
		}
	}

	/** Reload the account and permissions, e.g. after the account was edited. */
	async refresh(): Promise<void> {
		await this.loadSession();
	}

	async signIn(username: string, password: string): Promise<AuthResult> {
		try {
			const result = await apiSignIn({ body: { username, password } });
			if (result.error || !result.data) return { ok: false, message: authErrorMessage(result) };
			this.beginSession();
			if ((await this.loadSession()) !== 'signed-in') {
				return {
					ok: false,
					message: 'Signed in, but your account could not be loaded. Try again.'
				};
			}
			return { ok: true };
		} catch {
			return { ok: false, message: OFFLINE };
		}
	}

	/**
	 * Create the first administrator. The session cookie is set at once, but the
	 * account is not treated as signed in until `finishSetup`, so the page can
	 * show what happened to existing data first.
	 */
	async setup(username: string, displayName: string, password: string): Promise<SetupResult> {
		try {
			const result = await setupFirstAdmin({
				body: { username, display_name: displayName, password }
			});
			if (result.error || !result.data) return { ok: false, message: authErrorMessage(result) };
			this.beginSession();
			return { ok: true, claimed: result.data.claimed };
		} catch {
			return { ok: false, message: OFFLINE };
		}
	}

	async finishSetup(): Promise<void> {
		// Load first, so the guard never sees "set up, signed out" and bounces to sign-in.
		await this.loadSession();
		this.setupRequired = false;
	}

	/**
	 * Sign out. Local state is cleared first, so the route guard shows the sign-in page at once;
	 * the returned promise settles when the server has answered. If it did not end the session,
	 * the true state is reloaded so the page never claims a live session is over.
	 */
	async signOut(): Promise<AuthResult> {
		this.leftOnPurpose = true;
		this.clearSession();
		let failure: string | null = null;
		try {
			// keepalive lets the request finish even if the page navigates away meanwhile.
			const result = await apiSignOut({ keepalive: true });
			if (!result.response) failure = OFFLINE;
			// 401 means the session had already ended.
			else if (!result.response.ok && result.response.status !== 401) {
				failure = authErrorMessage(result);
			}
		} catch {
			failure = OFFLINE;
		}
		if (failure === null) return { ok: true };
		this.leftOnPurpose = false;
		await this.loadSession();
		return { ok: false, message: failure };
	}

	async changePassword(currentPassword: string, newPassword: string): Promise<AuthResult> {
		try {
			const result = await apiChangePassword({
				body: { current_password: currentPassword, new_password: newPassword }
			});
			if (result.error || !result.data) return { ok: false, message: authErrorMessage(result) };
			clearAllEtags();
			resetAuthEvents();
			await this.loadSession();
			return { ok: true };
		} catch {
			return { ok: false, message: OFFLINE };
		}
	}

	/** Start fresh: nothing cached for the previous person may show for the next. */
	private beginSession(): void {
		clearAllEtags();
		resetAuthEvents();
		this.leftOnPurpose = false;
	}

	private clearSession(): void {
		this.user = null;
		this.permissions = new Set();
		clearAllEtags();
	}

	private async loadSession(): Promise<SessionOutcome> {
		try {
			const me = await getCurrentUser();
			if (me.response?.status === 401) {
				this.clearSession();
				return 'signed-out';
			}
			if (me.error || !me.data) return 'failed';
			// An expired password makes content routes answer 403, so skip the call.
			const permissions = me.data.password_expired ? null : await getMyPermissions();
			this.user = me.data;
			this.permissions =
				!permissions || permissions.error || !permissions.data
					? new Set()
					: new Set(permissions.data.permissions);
			return 'signed-in';
		} catch {
			return 'failed';
		}
	}
}

export const auth = new AuthController();
