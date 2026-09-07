import { compare } from '@renovatebot/pep440';

interface VersionMismatch {
	frontend: string;
	backend: string;
}

function compareVersions(a: string, b: string): number | null {
	try {
		return compare(a, b);
	} catch {
		return null;
	}
}

class VersionController {
	mismatch = $state<VersionMismatch | null>(null);

	get backendNewer(): boolean {
		if (!this.mismatch) return false;
		// compare() returns null when either version is not valid PEP 440;
		// fall back to -1 (not newer) so the banner shows the safe "redeploy" path.
		return (compareVersions(this.mismatch.backend, this.mismatch.frontend) ?? -1) > 0;
	}

	report(backend: string): void {
		if (this.mismatch !== null) return;
		if (!__EXPECTED_BACKEND_VERSION__) return;
		if (compareVersions(backend, __EXPECTED_BACKEND_VERSION__) === 0) return;
		this.mismatch = { frontend: __EXPECTED_BACKEND_VERSION__, backend };
	}
}

export const versionController = new VersionController();
