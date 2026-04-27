"""Resolver registry and context-aware factory."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from services.dependency.base import DependencyResolver
from services.dependency.plugins.ros2 import Ros2AmentWorkspacePlugin, Ros2AttrPlugin, Ros2InterfacePlugin
from services.dependency.resolvers.cpp import CppResolver
from services.dependency.resolvers.python import PythonAttrPlugin, PythonImportPlugin, PythonResolver


@dataclass
class RepoContext:
    repo_path: PurePosixPath
    is_ros2: bool


def analyze_repository(repo_root: str) -> RepoContext:
    """Inspect repo_root to determine context (e.g. ROS 2 presence via package.xml)."""
    return RepoContext(
        repo_path=PurePosixPath(repo_root),
        is_ros2=Path(repo_root, "package.xml").exists(),
    )


def create_python_resolver(context: RepoContext) -> PythonResolver:
    """Build a PythonResolver with plugins appropriate for the given repo context."""
    plugins: list[PythonImportPlugin] = (
        [Ros2InterfacePlugin(), Ros2AmentWorkspacePlugin()] if context.is_ros2 else []
    )
    attr_plugins: list[PythonAttrPlugin] = [Ros2AttrPlugin()] if context.is_ros2 else []
    return PythonResolver(plugins=plugins, attr_plugins=attr_plugins)


def get_context_aware_registry(repo_root: str) -> dict[str, DependencyResolver]:
    """Return a resolver registry with context-appropriate Python plugin configuration."""
    context = analyze_repository(repo_root)
    python_resolver = create_python_resolver(context)
    cpp_resolver = CppResolver()
    return {
        ".cpp": cpp_resolver,
        ".cc": cpp_resolver,
        ".cxx": cpp_resolver,
        ".c": cpp_resolver,
        ".hpp": cpp_resolver,
        ".h": cpp_resolver,
        ".py": python_resolver,
    }


RESOLVER_REGISTRY: dict[str, DependencyResolver] = {
    ".cpp": CppResolver(),
    ".cc": CppResolver(),
    ".cxx": CppResolver(),
    ".c": CppResolver(),
    ".hpp": CppResolver(),
    ".h": CppResolver(),
    ".py": PythonResolver(),
}


def get_resolver(filename: str) -> DependencyResolver | None:
    """Look up a resolver by file extension."""
    ext = PurePosixPath(filename).suffix
    return RESOLVER_REGISTRY.get(ext)
