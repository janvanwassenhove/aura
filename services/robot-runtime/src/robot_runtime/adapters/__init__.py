"""Adapters sub-package."""

from robot_runtime.adapters.fake import FakeRobotAdapter

__all__ = ["FakeRobotAdapter"]

# ReachyRobotAdapter is NOT imported here: it needs the optional reachy-mini
# SDK (install with the [reachy] extra). Import it explicitly from
# robot_runtime.adapters.reachy where needed.
