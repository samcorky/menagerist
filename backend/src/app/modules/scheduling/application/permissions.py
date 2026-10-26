"""Administrative access to scheduled jobs and their run history."""

from typing import Self

from app.shared_kernel.permission import PermissionEnum


class SchedulingPermission(PermissionEnum):
    """Scheduler permissions remain administrative and non-content-scoped."""

    READ = "scheduling:job:read"
    RUN = "scheduling:job:run"

    def implied(self) -> frozenset[Self]:
        """Running a job also permits reading its state."""
        cls = type(self)
        return frozenset({cls.READ}) if self is cls.RUN else frozenset()
