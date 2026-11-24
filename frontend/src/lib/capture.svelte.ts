import type { AttributeRow } from '$lib/attribute-rows';
import type { RememberedConnection } from '$lib/capture-connection';
import type { AttributesSchema } from '$lib/schema-types';

export type StagedPhoto = {
	id: string;
	filename: string;
	previewUrl: string;
};

export type PendingCapture = {
	name: string;
	selectedType: string | null;
	stagedPhoto: StagedPhoto | null;
	/** The fields filled in, with a scanned code already placed in the field the person chose. */
	details: { rows: AttributeRow[]; extraSchema: AttributesSchema | null } | null;
};

class CaptureController {
	open = $state(false);
	nodeCreationCount = $state(0);
	pendingHandoff = $state<PendingCapture | null>(null);
	/** The last connection made while capturing, offered again until the page is reloaded. */
	lastConnection = $state<RememberedConnection | null>(null);

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
