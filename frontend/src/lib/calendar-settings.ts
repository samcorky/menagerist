import { preferences } from '$lib/preferences.svelte';

/** The day of the week as calendars number it: 0 is Sunday, 1 Monday, 6 Saturday. */
export type WeekDay = 0 | 1 | 2 | 3 | 4 | 5 | 6;

const FIXED: Record<string, WeekDay> = { monday: 1, sunday: 0, saturday: 6 };
/** Where the browser cannot say, weeks start on Monday (ISO 8601). */
const FALLBACK: WeekDay = 1;

type WeekInfoLocale = Intl.Locale & {
	getWeekInfo?: () => { firstDay: number };
	weekInfo?: { firstDay: number };
};

/** The usual first day of the week in `locale` (Intl numbers Monday 1 to Sunday 7). */
export function regionFirstDay(locale: string): WeekDay {
	try {
		const info = new Intl.Locale(locale) as WeekInfoLocale;
		const firstDay = info.getWeekInfo?.().firstDay ?? info.weekInfo?.firstDay;
		return typeof firstDay === 'number' && firstDay >= 1 && firstDay <= 7
			? ((firstDay % 7) as WeekDay)
			: FALLBACK;
	} catch {
		return FALLBACK;
	}
}

/** The first day for a `datetime.first_day` choice; anything unknown counts as automatic. */
export function firstDayFor(choice: unknown, locale: string): WeekDay {
	return typeof choice === 'string' && choice in FIXED ? FIXED[choice] : regionFirstDay(locale);
}

/** The signed-in person's first day of the week, from their preference and the browser. */
export function firstDayOfWeek(): WeekDay {
	const locale = typeof navigator === 'undefined' ? 'en-GB' : navigator.language;
	return firstDayFor(preferences.value('datetime.first_day'), locale);
}
