<script lang="ts">
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import {
		shortcutRegistry,
		formatKeys,
		isMacPlatform,
		type ShortcutGroup
	} from '$lib/shortcuts.svelte';

	let { open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void } = $props();

	const GROUP_ORDER: ShortcutGroup[] = ['Global', 'Search', 'Add item', 'Item'];

	let isMac = $derived(isMacPlatform());

	let grouped = $derived(
		GROUP_ORDER.map((group) => ({
			group,
			shortcuts: shortcutRegistry.active.filter((s) => s.group === group)
		})).filter((g) => g.shortcuts.length > 0)
	);
</script>

<ResponsiveDialog.Root {open} {onOpenChange}>
	<ResponsiveDialog.Content title="Keyboard shortcuts" size="md">
		<div class="mt-4 space-y-4">
			{#each grouped as { group, shortcuts } (group)}
				<div class="space-y-1.5">
					<h3 class="text-sm font-medium text-muted-foreground">{group}</h3>
					<ul class="space-y-1">
						{#each shortcuts as shortcut (shortcut.id)}
							<li class="flex items-center justify-between gap-4 text-sm">
								<span>{shortcut.description}</span>
								<kbd class="rounded border border-input bg-muted px-1.5 py-0.5 font-mono text-xs">
									{formatKeys(shortcut.keys, isMac)}
								</kbd>
							</li>
						{/each}
					</ul>
				</div>
			{/each}
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
