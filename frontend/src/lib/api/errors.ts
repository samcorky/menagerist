/**
 * Extract a human-readable message from a failed API call's `error` field.
 *
 * Covers both shapes the backend can return: an RFC 9457 problem detail
 * (`{ detail: string }`, from a domain error) and FastAPI's own request
 * validation error (`{ detail: Array<{ msg: string }> }`).
 */
export function errorMessage(error: unknown): string {
	if (error && typeof error === 'object' && 'detail' in error) {
		const detail = (error as { detail: unknown }).detail;
		if (typeof detail === 'string') {
			return detail;
		}
		if (Array.isArray(detail)) {
			return detail
				.map((item) =>
					item && typeof item === 'object' && 'msg' in item ? String(item.msg) : String(item)
				)
				.join(', ');
		}
	}
	return 'Something went wrong.';
}

/**
 * Returns a user-facing title + optional description appropriate for the
 * failure mode: offline, server error, or a domain/validation error.
 */
export function networkAwareError(result: { error?: unknown; response?: Response | null }): {
	title: string;
	description?: string;
} {
	if (!result.response) {
		return {
			title: 'You appear to be offline',
			description: 'Check your connection and try again.'
		};
	}
	if (result.response.status >= 500) {
		return {
			title: 'Something went wrong',
			description: 'Try again, or reload the page if the problem persists.'
		};
	}
	return { title: "Couldn't complete this action", description: errorMessage(result.error) };
}
