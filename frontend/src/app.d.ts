// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		interface PageState {
			/** Ids of the sheets and dialogs open on top of this history entry; see back-layer.svelte. */
			layers?: string[];
		}
		// interface Platform {}
	}
}

export {};
