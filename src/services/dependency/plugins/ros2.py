"""ROS 2 specific Python import plugins."""

from pathlib import PurePosixPath

from services.dependency.base import _STDLIB_MODULES
from services.dependency.resolvers.python import PythonImportPlugin

_ROS2_INTERFACE_TYPES: frozenset[str] = frozenset({"srv", "msg", "action"})


class Ros2InterfacePlugin(PythonImportPlugin):
    """Resolve ROS 2 interface imports (srv, msg, action)."""

    def resolve(
        self,
        from_module: str | None,
        imported_items: str | None,
        direct_module: str | None,
        file_dir: PurePosixPath,
    ) -> list[str] | None:

        if from_module is None or imported_items is None:
            return None
        parts = from_module.split(".")
        if not parts or parts[-1] not in _ROS2_INTERFACE_TYPES:
            return None

        interface_type = parts[-1]
        pkg_path = "/".join(parts[:-1])

        if not pkg_path:
            return None

        first_path = file_dir.parts[0]

        candidates: list[str] = []
        for item_raw in imported_items.split(","):
            item = item_raw.split(" as ")[0].strip()
            if not item or item == "*":
                continue
            candidates.append(f"{pkg_path}/{interface_type}/{item}.{interface_type}")
            candidates.append(f"{first_path}/{pkg_path}/{interface_type}/{item}.{interface_type}")

        return candidates if candidates else None


class Ros2AmentWorkspacePlugin(PythonImportPlugin):
    """Resolve absolute imports using the Ament workspace root-nesting convention."""

    def resolve(
        self,
        from_module: str | None,
        imported_items: str | None,
        direct_module: str | None,
        file_dir: PurePosixPath,
    ) -> list[str] | None:
        module = from_module or direct_module
        if module is None or module.startswith("."):
            return None

        parts = module.split(".")
        if len(parts) > 1 and parts[-1] in _ROS2_INTERFACE_TYPES:
            return None
        if len(parts) < 2:
            return None

        pkg_root = parts[0]
        if pkg_root in _STDLIB_MODULES:
            return None

        rest = "/".join(parts[1:])

        # If pkg_root appears in file_dir, anchor the path to the workspace location.
        # e.g. file_dir=src/giga_r1_driver/src, pkg_root=giga_r1_driver
        #   -> prefix=src/giga_r1_driver -> src/giga_r1_driver/giga_r1_driver/rest.py
        dir_parts = file_dir.parts
        if pkg_root in dir_parts:
            idx = list(dir_parts).index(pkg_root)
            prefix = str(PurePosixPath(*dir_parts[: idx + 1]))
            return [f"{prefix}/{pkg_root}/{rest}.py"]

        return [f"{pkg_root}/{pkg_root}/{rest}.py"]
