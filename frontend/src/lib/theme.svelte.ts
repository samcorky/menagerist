export type Theme = 'system' | 'light' | 'dark';

class ThemeController {
	theme = $state<Theme>('system');

	private applyTheme(t: Theme): void {
		if (typeof window === 'undefined') return;
		const dark =
			t === 'dark' || (t === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
		document.documentElement.classList.toggle('dark', dark);
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
