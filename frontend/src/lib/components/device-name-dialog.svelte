<script lang="ts">
	import { toast } from 'svelte-sonner';
	import {
		adoptDeviceName,
		listDeviceNameSuggestions,
		listOwnDevices,
		renameOwnDevice,
		type DeviceNameSuggestionResponse
	} from '$lib/api/client';
	import { errorMessage } from '$lib/api/errors';
	import { auth } from '$lib/auth.svelte.js';
	import { describeDevice } from '$lib/devices';
	import DeviceNamePrompt from '$lib/components/device-name-prompt.svelte';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';

	// "Not now" is remembered for the device, so signing in again does not ask again. The
	// pencil beside a device on the Account page still names it later.
	const DISMISSED_PREFIX = 'menagerist:device-name-dismissed:';
	let open = $state(false);
	let deviceId = $state<string | null>(null);
	let label = $state('');
	let suggestions = $state<DeviceNameSuggestionResponse[]>([]);

	function read(storage: () => Storage, key: string): string | null {
		try {
			return storage().getItem(key);
		} catch {
			return null;
		}
	}

	function write(storage: () => Storage, key: string, value: string) {
		try {
			storage().setItem(key, value);
		} catch {
			// Remembering is a convenience; the prompt may simply return.
		}
	}

	async function check() {
		try {
			const result = await listOwnDevices();
			const current = result.data?.find((d) => d.current && d.id && !d.name);
			if (!current?.id || read(() => localStorage, DISMISSED_PREFIX + current.id)) return;
			const found = await listDeviceNameSuggestions();
			suggestions = found.data ?? [];
			label = describeDevice({
				userAgent: current.user_agent,
				platform: current.platform,
				mobile: current.mobile,
				displayMode: current.sessions[0]?.display_mode
			}).label;
			deviceId = current.id;
			open = true;
		} catch {
			// Naming is optional, so a failed check is not worth interrupting anyone for.
		}
	}

	// Only an interactive sign-in asks; a page load or a session started elsewhere does not.
	$effect(() => {
		if (auth.deviceNamePromptDue && auth.signedIn && !auth.passwordExpired) {
			auth.deviceNamePromptDue = false;
			void check();
		}
	});

	function dismiss() {
		if (deviceId) write(() => localStorage, DISMISSED_PREFIX + deviceId, '1');
		open = false;
	}

	async function onname(name: string): Promise<boolean> {
		if (!deviceId) return false;
		try {
			const result = await renameOwnDevice({
				path: { device_id: deviceId },
				body: { name }
			});
			if (result.error) {
				toast.error(errorMessage(result.error));
				return false;
			}
			toast.success('Device named');
			open = false;
			return true;
		} catch {
			toast.error('Could not save the name.');
			return false;
		}
	}

	async function onadopt(fromDeviceId: string): Promise<boolean> {
		try {
			const result = await adoptDeviceName({ path: { device_id: fromDeviceId } });
			if (result.error) {
				toast.error(errorMessage(result.error));
				return false;
			}
			toast.success('Device named');
			open = false;
			return true;
		} catch {
			toast.error('Could not reuse that name.');
			return false;
		}
	}
</script>

<ResponsiveDialog.Root {open} onOpenChange={(v) => (v ? (open = true) : dismiss())}>
	<ResponsiveDialog.Content title="Name this device" size="sm">
		<ResponsiveDialog.Description>
			A name makes it easier to tell your devices apart when you sign one out.
		</ResponsiveDialog.Description>
		<div class="mt-4">
			<DeviceNamePrompt {label} {suggestions} {onname} {onadopt} ondismiss={dismiss} />
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
