"""Dependency resolution package — public API."""

from services.dependency.base import DependencyResolver
from services.dependency.plugins.ros2 import Ros2AmentWorkspacePlugin, Ros2AttrPlugin, Ros2InterfacePlugin
from services.dependency.registry import (
    RESOLVER_REGISTRY,
    RepoContext,
    analyze_repository,
    create_python_resolver,
    get_context_aware_registry,
    get_resolver,
)
from services.dependency.resolvers.cpp import CppResolver
from services.dependency.resolvers.python import PythonAttrPlugin, PythonImportPlugin, PythonResolver

__all__ = [
    "DependencyResolver",
    "PythonImportPlugin",
    "PythonAttrPlugin",
    "PythonResolver",
    "CppResolver",
    "Ros2InterfacePlugin",
    "Ros2AmentWorkspacePlugin",
    "Ros2AttrPlugin",
    "RepoContext",
    "RESOLVER_REGISTRY",
    "analyze_repository",
    "create_python_resolver",
    "get_context_aware_registry",
    "get_resolver",
]
