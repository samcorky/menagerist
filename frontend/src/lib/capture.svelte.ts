class CaptureController {
	open = $state(false);
	nodeCreationCount = $state(0);

	show() {
		this.open = true;
	}

	hide() {
		this.open = false;
	}

	toggle() {
		this.open = !this.open;
	}

	notifyNodeCreated() {
		this.nodeCreationCount++;
	}
}

export const captureController = new CaptureController();
