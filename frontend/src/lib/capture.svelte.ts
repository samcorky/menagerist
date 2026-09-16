export type StagedPhoto = {
	id: string;
	filename: string;
	previewUrl: string;
};

export type PendingCapture = {
	name: string;
	selectedType: string | null;
	stagedPhoto: StagedPhoto | null;
};

class CaptureController {
	open = $state(false);
	nodeCreationCount = $state(0);
	pendingHandoff = $state<PendingCapture | null>(null);

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

	setPendingHandoff(data: PendingCapture) {
		this.pendingHandoff = data;
	}

	consumePendingHandoff(): PendingCapture | null {
		const data = this.pendingHandoff;
		this.pendingHandoff = null;
		return data;
	}
}

export const captureController = new CaptureController();
