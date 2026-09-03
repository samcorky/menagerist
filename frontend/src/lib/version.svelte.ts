interface VersionMismatch {
	frontend: string;
	backend: string;
}

class VersionController {
	mismatch = $state<VersionMismatch | null>(null);

	report(backend: string): void {
		if (this.mismatch !== null) return;
		if (!__EXPECTED_BACKEND_VERSION__) return;
		if (backend === __EXPECTED_BACKEND_VERSION__) return;
		this.mismatch = { frontend: __EXPECTED_BACKEND_VERSION__, backend };
	}
}

export const versionController = new VersionController();
