import type { Component } from 'svelte';
import {
	Activity,
	CalendarClock,
	Database,
	Gauge,
	GitBranch,
	HardDrive,
	HeartPulse,
	Network,
	PackageCheck,
	Pencil,
	Server,
	ShieldCheck,
	Wrench
} from '@lucide/svelte';

export type StatusIconName =
	| 'activity'
	| 'calendar'
	| 'database'
	| 'gauge'
	| 'branch'
	| 'disk'
	| 'heartbeat'
	| 'network'
	| 'package'
	| 'pencil'
	| 'shield'
	| 'server'
	| 'wrench';

const ICONS: Record<StatusIconName, Component> = {
	activity: Activity,
	calendar: CalendarClock,
	database: Database,
	gauge: Gauge,
	branch: GitBranch,
	disk: HardDrive,
	heartbeat: HeartPulse,
	network: Network,
	package: PackageCheck,
	pencil: Pencil,
	shield: ShieldCheck,
	server: Server,
	wrench: Wrench
};

/** What a check with no recognised name gets; a known check must never land on it. */
export const FALLBACK_METRIC_ICON: StatusIconName = 'wrench';
/** What a group with no recognised name gets. */
export const FALLBACK_GROUP_ICON: StatusIconName = 'server';

/** `proxyInsecureOrigin` -> `Proxy Insecure Origin`. */
export function formatLabel(camel: string): string {
	return camel
		.replace(/([A-Z])/g, ' $1')
		.replace(/^./, (s) => s.toUpperCase())
		.replace(/\bCors\b/g, 'CORS');
}

export function formatGroup(key: string): string {
	return key.charAt(0).toUpperCase() + key.slice(1);
}

export function groupIconName(key: string): StatusIconName {
	if (key === 'database') return 'database';
	if (key === 'system') return 'activity';
	if (key === 'pool') return 'gauge';
	if (key === 'migration') return 'branch';
	if (key === 'configuration' || key === 'proxy') return 'network';
	if (key === 'storage') return 'disk';
	if (key === 'scheduler') return 'calendar';
	return FALLBACK_GROUP_ICON;
}

export function metricIconName(label: string): StatusIconName {
	const lower = label.toLowerCase();
	if (lower.includes('proxy') || lower.includes('cors')) return 'network';
	if (lower.includes('database') || lower.includes('db')) return 'database';
	if (lower.includes('migration') || lower.includes('schema')) return 'branch';
	if (lower.includes('pool') || lower.includes('connection')) return 'gauge';
	if (lower.includes('storage') || lower.includes('space')) return 'disk';
	if (lower.includes('writable')) return 'pencil';
	if (lower.includes('version') || lower.includes('build')) return 'package';
	if (lower.includes('health') || lower.includes('status')) return 'shield';
	if (lower.includes('heartbeat')) return 'heartbeat';
	if (lower.includes('response')) return 'activity';
	return FALLBACK_METRIC_ICON;
}

export const groupIcon = (key: string): Component => ICONS[groupIconName(key)];
export const metricIcon = (label: string): Component => ICONS[metricIconName(label)];
