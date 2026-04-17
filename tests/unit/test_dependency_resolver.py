from services.dependency_resolver import (
    RESOLVER_REGISTRY,
    CppResolver,
    PythonResolver,
    get_resolver,
)


class TestCppResolver:
    def test_quoted_include_same_dir(self) -> None:
        resolver = CppResolver()
        diff = '+#include "my_node.hpp"'
        paths = resolver.guess_paths("src/nodes/my_node.cpp", diff, "org/my_pkg")
        assert any("src/nodes/my_node.hpp" in p for p in paths)

    def test_quoted_include_guesses_paths(self) -> None:
        resolver = CppResolver()
        diff = '+#include "my_node.hpp"'
        paths = resolver.guess_paths("src/my_node.cpp", diff, "org/my_pkg")
        assert "src/my_node.hpp" in paths
        assert "include/my_node.hpp" in paths
        assert "include/my_pkg/my_node.hpp" in paths

    def test_angle_bracket_include(self) -> None:
        resolver = CppResolver()
        paths = resolver.guess_paths("src/node.cpp", "+#include <rclcpp/rclcpp.hpp>", "org/my_pkg")
        assert "include/rclcpp/rclcpp.hpp" in paths
        assert "include/my_pkg/rclcpp/rclcpp.hpp" in paths

    def test_no_includes_returns_empty(self) -> None:
        resolver = CppResolver()
        paths = resolver.guess_paths("src/main.cpp", "+int x = 1;", "org/pkg")
        assert paths == []

    def test_deduplicates_paths(self) -> None:
        resolver = CppResolver()
        diff = '+#include "foo.h"\n+#include "foo.h"'
        paths = resolver.guess_paths("src/a.cpp", diff, "org/pkg")
        assert paths.count("src/foo.h") == 1

    def test_root_dir_file(self) -> None:
        resolver = CppResolver()
        paths = resolver.guess_paths("main.cpp", '+#include "utils.h"', "org/pkg")
        assert "utils.h" in paths
        assert "include/utils.h" in paths


class TestPythonResolver:
    def test_from_import(self) -> None:
        resolver = PythonResolver()
        paths = resolver.guess_paths("src/app.py", "+from utils import helper", "org/repo")
        assert "utils.py" in paths

    def test_dotted_import(self) -> None:
        resolver = PythonResolver()
        paths = resolver.guess_paths("src/app.py", "+from a.b.c import func", "org/repo")
        assert "a/b/c.py" in paths

    def test_dotted_leading_import(self) -> None:
        resolver = PythonResolver()
        paths = resolver.guess_paths(
            "src/giga_r1_driver/giga_r1_driver/publisher_registry.py",
            "from .decoders.base import BaseDecoder",
            "org/repo",
        )
        assert "src/giga_r1_driver/giga_r1_driver/decoders/base.py" in paths

    def test_bare_import(self) -> None:
        resolver = PythonResolver()
        paths = resolver.guess_paths("app.py", "+import my_module", "org/repo")
        assert "my_module.py" in paths

    def test_filters_stdlib(self) -> None:
        resolver = PythonResolver()
        paths = resolver.guess_paths("app.py", "+import os\n+import sys\n+import json", "org/repo")
        assert paths == []

    def test_mixed_stdlib_and_local(self) -> None:
        resolver = PythonResolver()
        paths = resolver.guess_paths("app.py", "+import os\n+from my_lib import foo", "org/repo")
        assert len(paths) == 1
        assert "my_lib.py" in paths

    def test_no_imports_returns_empty(self) -> None:
        resolver = PythonResolver()
        paths = resolver.guess_paths("app.py", "+x = 1\n+y = 2", "org/repo")
        assert paths == []

    def test_does_not_include_removed_lines(self) -> None:
        resolver = PythonResolver()
        paths = resolver.guess_paths("app.py", "-import my_lib\n+x = 1", "org/repo")
        assert paths == []


class TestGetResolver:
    def test_python_file(self) -> None:
        resolver = get_resolver("src/app.py")
        assert isinstance(resolver, PythonResolver)

    def test_cpp_file(self) -> None:
        resolver = get_resolver("src/node.cpp")
        assert isinstance(resolver, CppResolver)

    def test_cc_file(self) -> None:
        resolver = get_resolver("src/node.cc")
        assert isinstance(resolver, CppResolver)

    def test_hpp_file(self) -> None:
        resolver = get_resolver("include/node.hpp")
        assert isinstance(resolver, CppResolver)

    def test_unknown_extension_returns_none(self) -> None:
        assert get_resolver("README.md") is None
        assert get_resolver("styles.css") is None
        assert get_resolver("Makefile") is None

    def test_registry_has_expected_extensions(self) -> None:
        assert set(RESOLVER_REGISTRY.keys()) == {".cpp", ".cc", ".cxx", ".c", ".hpp", ".h", ".py"}
