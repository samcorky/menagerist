import iso from '$shared/data/iso-data.json';

/** A currency option: three-letter code, common name, and symbol when one exists. */
export type Currency = { code: string; name: string; symbol?: string };

// Single-symbol currencies only: where one common symbol is unambiguous. Everything else
// falls back to "{value} {code}" in the view. Codes and names come from shared/data/iso-data.json.
const SYMBOLS: Record<string, string> = {
	ARS: '$',
	AUD: '$',
	BRL: 'R$',
	CAD: '$',
	CNY: '¥',
	CZK: 'Kč',
	EUR: '€',
	GBP: '£',
	HKD: 'HK$',
	ILS: '₪',
	INR: '₹',
	JPY: '¥',
	KRW: '₩',
	MXN: '$',
	MYR: 'RM',
	NGN: '₦',
	NZD: '$',
	PHP: '₱',
	PLN: 'zł',
	RUB: '₽',
	SGD: 'S$',
	THB: '฿',
	TRY: '₺',
	TWD: 'NT$',
	UAH: '₴',
	USD: '$',
	VND: '₫',
	ZAR: 'R'
};

export const CURRENCIES: Currency[] = iso.currencies.map(({ code, name }) => {
	const symbol = SYMBOLS[code];
	return symbol ? { code, name, symbol } : { code, name };
});

const byCode = new Map(CURRENCIES.map((c) => [c.code, c]));

export function currencyByCode(code: string): Currency | undefined {
	return byCode.get(code);
}
