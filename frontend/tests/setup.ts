const mockState = Object.assign(<T>(value: T): T => value, {
	raw: <T>(value: T): T => value,
	snapshot: <T>(value: T): T => value,
	eager: <T>(value: T): T => value
});

Object.assign(globalThis, {
	$state: mockState
});

export {};
