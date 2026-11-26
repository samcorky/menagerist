<script lang="ts">
	import * as ResponsiveDialog from '$lib/components/ui/responsive-dialog/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import type { ParentChangeQuestion } from '$lib/parent-change';

	// Asked when changing an item type's parent would merge fields the type and its new parent
	// both have, or take away the fields it used from the old one. Items are never changed: they
	// keep every value, so the question is only about the type's own fields.
	let {
		open,
		question,
		typeLabel,
		previousLabel,
		parentLabel,
		fieldLabels,
		busy = false,
		onconfirm,
		oncancel
	}: {
		open: boolean;
		question: Exclude<ParentChangeQuestion, { kind: 'none' } | { kind: 'blocked' }> | null;
		typeLabel: string;
		/** The parent type it has now, when it has one. */
		previousLabel?: string | null;
		/** The parent type it is moving to, if any. */
		parentLabel?: string | null;
		/** A field's name from its key. */
		fieldLabels: (key: string) => string;
		busy?: boolean;
		onconfirm: (choice: { onClash: 'merge'; onDetach: 'keep' | 'drop' }) => void;
		oncancel: () => void;
	} = $props();

	const id = $props.id();
	let onDetach = $state<'keep' | 'drop'>('keep');
	$effect(() => {
		if (open) onDetach = 'keep';
	});

	const names = (keys: readonly string[]) => keys.map(fieldLabels).join(', ');
	const leaving = $derived(question?.kind === 'detach' || question?.kind === 'move');
	const merging = $derived(question?.kind === 'merge' || question?.kind === 'move');
	// The fields both the type and its new parent define, when there are any.
	const merged = $derived(
		question?.kind === 'merge' ? question.fields : question?.kind === 'move' ? question.merge : []
	);
	const title = $derived(
		question?.kind === 'merge'
			? 'Merge the shared fields?'
			: question?.kind === 'detach'
				? `Make ${typeLabel} a top-level type?`
				: 'Move to another parent type?'
	);
	const confirmLabel = $derived(
		question?.kind === 'merge'
			? 'Merge fields'
			: question?.kind === 'detach'
				? 'Make top-level'
				: 'Move'
	);
	const options = $derived([
		{
			value: 'keep' as const,
			label: `Keep the fields on ${typeLabel}`,
			hint: `${typeLabel} keeps ${previousLabel ?? 'its parent type'}'s fields as its own, so nothing changes about what an item holds.`
		},
		{
			value: 'drop' as const,
			label: 'Hide the fields',
			hint: 'They are archived: the values stay on the items, and you can bring the fields back later.'
		}
	]);
</script>

<ResponsiveDialog.Root {open} onOpenChange={(next) => !next && !busy && oncancel()}>
	<ResponsiveDialog.Content {title} size="sm">
		{#if question}
			<div class="space-y-4 text-sm">
				{#if leaving && question.kind !== 'merge'}
					<p>
						{typeLabel} will stop being a subtype of {previousLabel ?? 'its parent type'}.
						{#if question.items > 0}
							Its {question.items === 1 ? 'item keeps' : `${question.items} items keep`} every value
							{question.items === 1 ? 'it holds' : 'they hold'}.
						{/if}
					</p>
					<div role="radiogroup" aria-label="Fields from {previousLabel}" class="grid gap-2">
						{#each options as option (option.value)}
							<label
								class="flex cursor-pointer items-start gap-3 rounded-md border border-input p-3 has-checked:border-primary has-checked:bg-accent/40 has-focus-visible:ring-1 has-focus-visible:ring-ring pointer-coarse:min-h-11"
							>
								<input
									type="radio"
									name="detach-{id}"
									value={option.value}
									checked={onDetach === option.value}
									onchange={() => (onDetach = option.value)}
									aria-labelledby="{id}-{option.value}-label"
									aria-describedby="{id}-{option.value}-hint"
									class="mt-0.5 size-4 shrink-0 accent-primary"
								/>
								<span class="min-w-0">
									<span id="{id}-{option.value}-label" class="block font-medium">
										{option.label}
									</span>
									<span id="{id}-{option.value}-hint" class="block text-muted-foreground">
										{option.hint}
									</span>
									<span class="mt-1 block text-xs text-muted-foreground">
										{names(question.fields)}
									</span>
								</span>
							</label>
						{/each}
					</div>
				{/if}
				{#if merging}
					<p>
						{typeLabel} and {parentLabel} both have
						{names(merged)}. {typeLabel} will use
						{parentLabel}'s version of each. Where it is a list of choices, the options are
						combined, so nothing already saved stops being one of them. Items keep every value.
					</p>
				{/if}
			</div>
		{/if}
		<div class="mt-4 flex justify-end gap-2">
			<Button
				type="button"
				variant="outline"
				class="pointer-coarse:h-11"
				disabled={busy}
				onclick={oncancel}
			>
				Cancel
			</Button>
			<Button
				type="button"
				class="pointer-coarse:h-11"
				disabled={busy}
				onclick={() => onconfirm({ onClash: 'merge', onDetach })}
			>
				{busy ? 'Saving…' : confirmLabel}
			</Button>
		</div>
	</ResponsiveDialog.Content>
</ResponsiveDialog.Root>
