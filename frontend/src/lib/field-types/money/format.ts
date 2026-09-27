import { currencyByCode } from './currencies';

/**
 * View text for a money's stored `{value, currency}` object: a two-decimal, symbol-prefixed
 * amount when the currency's symbol is known ("£45.00"), "{value} {code}" otherwise ("45.00 XYZ"),
 * just the amount or just the code when only one half is set, or "" when both are empty.
 */
export function moneyText(raw: unknown): string {
	if (typeof raw !== 'object' || raw === null) return '';
	const { value, currency } = raw as { value?: unknown; currency?: unknown };
	// Read-mode callers pass this through `attributesToRows`, which stringifies every sub-value
	// of an object-typed field - so a numeric `value` may arrive as the string "45", not 45.
	const numeric =
		typeof value === 'number'
			? value
			: typeof value === 'string' && value !== ''
				? Number(value)
				: undefined;
	const amount = numeric !== undefined && !isNaN(numeric) ? numeric.toFixed(2) : undefined;
	const code = typeof currency === 'string' && currency !== '' ? currency : undefined;

	if (amount === undefined) return code ?? '';
	if (code === undefined) return amount;
	const symbol = currencyByCode(code)?.symbol;
	return symbol ? `${symbol}${amount}` : `${amount} ${code}`;
}
