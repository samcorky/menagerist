/** Fraction of a sheet's height it must be pulled down before letting go closes it. */
export const CLOSE_DISTANCE_FRACTION = 0.3;

/** Downward speed (px/ms) at which a flick closes the sheet however far it travelled. */
export const CLOSE_VELOCITY = 0.5;

/** Whether releasing a downward drag should close the sheet or let it spring back. */
export function shouldCloseSheet(distance: number, height: number, velocity: number): boolean {
	if (distance <= 0) return false;
	return distance >= height * CLOSE_DISTANCE_FRACTION || velocity >= CLOSE_VELOCITY;
}
