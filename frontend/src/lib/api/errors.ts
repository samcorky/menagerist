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
