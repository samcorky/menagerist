import { formatDistance } from 'date-fns';

export const NO_EXPORTS_MESSAGE = 'No exports. They are kept for 24 hours.';

/** "12.3 KB" below 1 MB, otherwise "4.5 MB". */
export function formatExportSize(bytes: number): string {
	return bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}

/** "Expires in about 23 hours", "Expires in 5 minutes" or "Expired". */
export function describeExportExpiry(expiresAt: string, now: Date): string {
	const expires = new Date(expiresAt);
	if (isNaN(expires.getTime())) return 'Expires soon';
	const remaining = expires.getTime() - now.getTime();
	if (remaining <= 0) return 'Expired';
	if (remaining < 60_000) return 'Expires in under a minute';
	return `Expires ${formatDistance(expires, now, { addSuffix: true })}`;
}
