<script lang="ts">
	import PlanPreview from '$lib/components/plan-preview.svelte';
	import type { ImportPlan } from '$lib/import-plan';
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';

	let {
		open,
		title,
		description,
		plan,
		loading = false,
		error = null,
		busy = false,
		confirmLabel,
		busyLabel,
		onOpenChange,
		onConfirm
	}: {
		open: boolean;
		title: string;
		description?: string;
		plan: ImportPlan | null;
		loading?: boolean;
		error?: string | null;
		busy?: boolean;
		confirmLabel?: string;
		busyLabel?: string;
		onOpenChange: (open: boolean) => void;
		onConfirm: () => void;
	} = $props();
</script>

<ResponsiveDialog.Root {open} {onOpenChange}>
	<ResponsiveDialog.Content {title} size="md">
		{#if description}
			<ResponsiveDialog.Description>{description}</ResponsiveDialog.Description>
		{/if}
		<div class="mt-4">
			<PlanPreview
				{plan}
				{loading}
				{error}
				{busy}
				{confirmLabel}
				{busyLabel}
				onCancel={() => onOpenChange(false)}
				{onConfirm}
			/>
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
