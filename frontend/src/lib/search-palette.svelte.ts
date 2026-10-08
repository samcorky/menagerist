class SearchPaletteController {
	open = $state(false);

	show() {
		this.open = true;
	}

	hide() {
		this.open = false;
	}
}

export const searchPaletteController = new SearchPaletteController();
