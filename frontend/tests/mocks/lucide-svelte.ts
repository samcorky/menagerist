// Stub for @lucide/svelte in tests (aliased in vitest.config.ts). The real
// package's barrel exports thousands of icon components, which Vitest's
// Node/SSR pipeline transforms one by one (no browser-style dep pre-bundling
// applies there) - importing it directly adds well over a minute to every
// test run. Tests here never render icons, only exercise pure logic from
// component module scripts, so a null stand-in is fine for every icon.
// Add a name here if a newly-used icon makes an import fail.
const stub = null as unknown as never;

export const Activity = stub;
export const AlertCircle = stub;
export const ArrowLeftRight = stub;
export const BookOpen = stub;
export const Camera = stub;
export const Check = stub;
export const ChevronLeft = stub;
export const ChevronRight = stub;
export const CirclePlus = stub;
export const Download = stub;
export const File = stub;
export const House = stub;
export const ImagePlus = stub;
export const LayoutGrid = stub;
export const List = stub;
export const Monitor = stub;
export const Moon = stub;
export const Package = stub;
export const PackageSearch = stub;
export const Pencil = stub;
export const Plus = stub;
export const SearchX = stub;
export const ServerCrash = stub;
export const Settings = stub;
export const Star = stub;
export const StarOff = stub;
export const Sun = stub;
export const Tag = stub;
export const Telescope = stub;
export const Trash2 = stub;
export const TriangleAlert = stub;
export const Upload = stub;
export const X = stub;
