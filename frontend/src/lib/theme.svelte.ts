export type Theme = 'system' | 'light' | 'dark';

/**
 * The page background in each theme, as the browser or installed app's title bar colour. These
 * match `--background` in layout.css; app.html and static/manifest.webmanifest repeat the light one.
 */
export const THEME_COLOURS = { light: '#ffffff', dark: '#0a0a0a' } as const;

class ThemeController {
	theme = $state<Theme>('system');

	private applyTheme(t: Theme): void {
		if (typeof window === 'undefined') return;
		const dark =
			t === 'dark' || (t === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
		document.documentElement.classList.toggle('dark', dark);
		document
			.querySelector('meta[name="theme-color"]')
			?.setAttribute('content', dark ? THEME_COLOURS.dark : THEME_COLOURS.light);
	}

	init(): void {
		if (typeof window === 'undefined') return;
		const saved = localStorage.getItem('theme') as Theme | null;
		this.theme = saved ?? 'system';
		window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
			if (this.theme === 'system') this.applyTheme('system');
		});
	}

	set(t: Theme): void {
		this.theme = t;
		if (typeof window !== 'undefined') {
			localStorage.setItem('theme', t);
			this.applyTheme(t);
		}
	}

	cycle(): void {
		const order: Theme[] = ['system', 'light', 'dark'];
		this.set(order[(order.indexOf(this.theme) + 1) % order.length]);
	}
}

export const themeController = new ThemeController();
