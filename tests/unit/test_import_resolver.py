"""Tests for the multi-language import resolver."""



from agents.import_resolver import (
    _CppExtractor,
    _GoExtractor,
    _JavaExtractor,
    _JSExtractor,
    _PHPExtractor,
    _PythonExtractor,
    _RubyExtractor,
    _RustExtractor,
    resolve_imports,
)

# ---- Python ----


class TestPythonExtractor:
    def test_from_import(self):
        diff = "+from utils import helper, formatter"
        ext = _PythonExtractor()
        raw = ext.extract(diff)
        assert len(raw) == 1
        assert raw[0][0] == "utils"
        assert raw[0][1] == ["helper", "formatter"]

    def test_direct_import(self):
        diff = "+import os\n+import json, csv"
        ext = _PythonExtractor()
        raw = ext.extract(diff)
        assert len(raw) == 3
        modules = [r[0] for r in raw]
        assert "os" in modules
        assert "json" in modules
        assert "csv" in modules

    def test_context_lines_also_parsed(self):
        """Imports in context lines (space prefix) should also be found."""
        diff = " from utils import helper\n+some_addition\n-import json"
        ext = _PythonExtractor()
        raw = ext.extract(diff)
        modules = [r[0] for r in raw]
        assert "utils" in modules
        assert "json" in modules

    def test_to_repo_paths_from_import(self):
        diff = "+from custom_interfaces.msg import MyMsg"
        ext = _PythonExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "ws/src/custom_interfaces/msg/MyMsg.msg",
            "ws/src/custom_interfaces/msg/__init__.py",
            "ws/src/custom_interfaces/CMakeLists.txt",
        ]
        paths = ext.to_repo_paths(raw, "ws/src/my_node/my_node/script.py", repo_tree)
        assert "ws/src/custom_interfaces/msg/MyMsg.msg" in paths

    def test_to_repo_paths_direct_import(self):
        diff = "+import utils"
        ext = _PythonExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "src/utils.py",
            "src/utils/__init__.py",
            "tests/utils.py",
        ]
        paths = ext.to_repo_paths(raw, "src/app.py", repo_tree)
        assert "src/utils.py" in paths

    def test_to_repo_paths_relative_import(self):
        diff = "+from . import sibling"
        ext = _PythonExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "src/pkg/sibling.py",
            "src/pkg/sibling/__init__.py",
            "src/pkg/main.py",
        ]
        paths = ext.to_repo_paths(raw, "src/pkg/main.py", repo_tree)
        assert "src/pkg/sibling.py" in paths

    def test_ros2_interface_suffix(self):
        diff = "+from my_pkg.srv import AddTwoInts"
        ext = _PythonExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "src/my_pkg/srv/AddTwoInts.srv",
            "src/my_pkg/srv/__init__.py",
        ]
        paths = ext.to_repo_paths(raw, "src/client.py", repo_tree)
        assert "src/my_pkg/srv/AddTwoInts.srv" in paths

    def test_stdlib_filtered(self):
        diff = "+import os\n+import json"
        ext = _PythonExtractor()
        raw = ext.extract(diff)
        repo_tree = ["src/os.py"]
        paths = ext.to_repo_paths(raw, "src/app.py", repo_tree)
        # stdlib os is filtered — should not return even if file exists
        assert "src/os.py" not in paths


# ---- JavaScript / TypeScript ----


class TestJSExtractor:
    def test_import_from(self):
        diff = "+import { Button } from './components/Button'"
        ext = _JSExtractor()
        raw = ext.extract(diff)
        assert len(raw) == 1
        assert raw[0][0] == "./components/Button"

    def test_require(self):
        diff = "+const utils = require('./utils')"
        ext = _JSExtractor()
        raw = ext.extract(diff)
        assert raw[0][0] == "./utils"

    def test_dynamic_import(self):
        diff = "+const mod = await import('./lazy')"
        ext = _JSExtractor()
        raw = ext.extract(diff)
        assert raw[0][0] == "./lazy"

    def test_skip_npm_packages(self):
        diff = "+import React from 'react'\n+import { useState } from 'react'"
        ext = _JSExtractor()
        raw = ext.extract(diff)
        assert len(raw) == 0

    def test_to_repo_paths_relative(self):
        diff = "+import { Button } from './components/Button'"
        ext = _JSExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "src/components/Button.tsx",
            "src/components/Button/index.tsx",
            "src/components/Button.ts",
        ]
        paths = ext.to_repo_paths(raw, "src/App.tsx", repo_tree)
        assert "src/components/Button.tsx" in paths
        assert "src/components/Button/index.tsx" in paths

    def test_to_repo_paths_alias(self):
        diff = "+import { foo } from '@/lib/utils'"
        ext = _JSExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "src/lib/utils.ts",
        ]
        paths = ext.to_repo_paths(raw, "src/App.tsx", repo_tree)
        assert "src/lib/utils.ts" in paths


# ---- Go ----


class TestGoExtractor:
    def test_single_import(self):
        diff = '+import "github.com/myorg/myrepo/pkg/util"'
        ext = _GoExtractor()
        raw = ext.extract(diff)
        assert len(raw) == 1
        assert raw[0][0] == "github.com/myorg/myrepo/pkg/util"

    def test_block_import(self):
        diff = '+import (\n+    "fmt"\n+    "github.com/org/repo/internal/db"\n+    "os"\n+)'
        ext = _GoExtractor()
        raw = ext.extract(diff)
        modules = [r[0] for r in raw]
        assert "fmt" not in modules  # stdlib
        assert "os" not in modules  # stdlib
        assert "github.com/org/repo/internal/db" in modules

    def test_skip_stdlib(self):
        diff = '+import "fmt"\n+import "strings"'
        ext = _GoExtractor()
        raw = ext.extract(diff)
        assert len(raw) == 0


# ---- Java / Kotlin ----


class TestJavaExtractor:
    def test_java_import(self):
        diff = "+import com.example.service.UserService;"
        ext = _JavaExtractor()
        raw = ext.extract(diff)
        assert len(raw) == 1
        assert raw[0][0] == "com.example.service.UserService"

    def test_kotlin_import_no_semicolon(self):
        diff = "+import com.example.service.UserService"
        ext = _JavaExtractor()
        raw = ext.extract(diff)
        assert raw[0][0] == "com.example.service.UserService"

    def test_skip_stdlib(self):
        diff = "+import java.util.List;\n+import kotlin.collections.Map"
        ext = _JavaExtractor()
        raw = ext.extract(diff)
        assert len(raw) == 0

    def test_wildcard_import(self):
        diff = "+import com.example.service.*;"
        ext = _JavaExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "src/com/example/service/UserService.java",
            "src/com/example/service/OrderService.java",
        ]
        paths = ext.to_repo_paths(raw, "src/com/example/controller/UserController.java", repo_tree)
        assert len(paths) == 2

    def test_to_repo_paths_class_match(self):
        diff = "+import com.example.model.User"
        ext = _JavaExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "src/com/example/model/User.java",
            "src/com/example/model/User.kt",
        ]
        paths = ext.to_repo_paths(raw, "src/com/example/Main.java", repo_tree)
        assert "src/com/example/model/User.java" in paths


# ---- Rust ----


class TestRustExtractor:
    def test_use_crate(self):
        diff = "+use crate::services::auth;"
        ext = _RustExtractor()
        raw = ext.extract(diff)
        assert raw[0][0] == "crate::services::auth"

    def test_mod(self):
        diff = "+mod payments;"
        ext = _RustExtractor()
        raw = ext.extract(diff)
        assert raw[0][0] == "mod:payments"

    def test_skip_stdlib(self):
        diff = "+use std::collections::HashMap;\n+use core::sync::atomic"
        ext = _RustExtractor()
        raw = ext.extract(diff)
        assert len(raw) == 0

    def test_to_repo_paths_crate(self):
        diff = "+use crate::models::user;"
        ext = _RustExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "src/models/user.rs",
            "src/models/user/mod.rs",
        ]
        paths = ext.to_repo_paths(raw, "src/main.rs", repo_tree)
        assert "src/models/user.rs" in paths
        assert "src/models/user/mod.rs" in paths

    def test_to_repo_paths_mod_sibling(self):
        diff = "+mod config;"
        ext = _RustExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "src/lib.rs",
            "src/config.rs",
        ]
        paths = ext.to_repo_paths(raw, "src/lib.rs", repo_tree)
        assert "src/config.rs" in paths


# ---- C / C++ ----


class TestCppExtractor:
    def test_quoted_include(self):
        diff = '+#include "utils.hpp"'
        ext = _CppExtractor()
        raw = ext.extract(diff)
        assert raw[0][0] == "utils.hpp"

    def test_skip_system_include(self):
        diff = '+#include <iostream>\n+#include "local.h"'
        ext = _CppExtractor()
        raw = ext.extract(diff)
        assert len(raw) == 1
        assert raw[0][0] == "local.h"

    def test_to_repo_paths_relative(self):
        diff = '+#include "messages/Header.h"'
        ext = _CppExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "src/messages/Header.h",
            "include/messages/Header.h",
        ]
        paths = ext.to_repo_paths(raw, "src/node.cpp", repo_tree)
        assert "src/messages/Header.h" in paths
        assert "include/messages/Header.h" in paths


# ---- PHP ----


class TestPHPExtractor:
    def test_use_namespace(self):
        diff = "+use App\\Service\\UserService;"
        ext = _PHPExtractor()
        raw = ext.extract(diff)
        assert raw[0][0] == "App\\Service\\UserService"

    def test_require_relative(self):
        diff = "+require_once './helpers.php';"
        ext = _PHPExtractor()
        raw = ext.extract(diff)
        assert raw[0][0] == "./helpers.php"

    def test_to_repo_paths_namespace(self):
        diff = "+use App\\Models\\User;"
        ext = _PHPExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "app/Models/User.php",
            "src/Models/User.php",
        ]
        paths = ext.to_repo_paths(raw, "app/Http/Controllers/UserController.php", repo_tree)
        assert "app/Models/User.php" in paths


# ---- Ruby ----


class TestRubyExtractor:
    def test_require_relative(self):
        diff = "+require_relative './config'"
        ext = _RubyExtractor()
        raw = ext.extract(diff)
        assert raw[0][0] == "./config"

    def test_require_with_path(self):
        diff = "+require 'lib/auth'"
        ext = _RubyExtractor()
        raw = ext.extract(diff)
        assert raw[0][0] == "lib/auth"

    def test_skip_stdlib_gem(self):
        diff = "+require 'json'\n+require 'csv'"
        ext = _RubyExtractor()
        raw = ext.extract(diff)
        # single-word bare requires are skipped
        assert len(raw) == 0

    def test_to_repo_paths_relative(self):
        diff = "+require_relative '../models/user'"
        ext = _RubyExtractor()
        raw = ext.extract(diff)
        repo_tree = [
            "app/models/user.rb",
        ]
        paths = ext.to_repo_paths(raw, "app/controllers/users_controller.rb", repo_tree)
        assert "app/models/user.rb" in paths


# ---- Integration: resolve_imports ----


class TestResolveImports:
    def test_python_integration(self):
        diff = "+from utils import helper\n+import json"
        repo_tree = [
            "src/utils.py",
            "src/app.py",
            "tests/utils.py",
        ]
        paths = resolve_imports("src/app.py", diff, repo_tree)
        assert "src/utils.py" in paths
        # stdlib json should be filtered
        assert not any("json.py" in p for p in paths)

    def test_ros2_integration(self):
        diff = "+from custom_interfaces.msg import MyMsg\n+from my_pkg.srv import AddTwoInts"
        repo_tree = [
            "ws/src/custom_interfaces/msg/MyMsg.msg",
            "ws/src/custom_interfaces/msg/__init__.py",
            "ws/src/my_pkg/srv/AddTwoInts.srv",
            "ws/src/my_pkg/src/client.py",
        ]
        paths = resolve_imports("ws/src/my_pkg/src/client.py", diff, repo_tree)
        assert "ws/src/custom_interfaces/msg/MyMsg.msg" in paths
        assert "ws/src/my_pkg/srv/AddTwoInts.srv" in paths

    def test_typescript_integration(self):
        diff = "+import { Button } from './components/Button'"
        repo_tree = [
            "src/components/Button.tsx",
            "src/components/Button/index.tsx",
            "src/App.tsx",
        ]
        paths = resolve_imports("src/App.tsx", diff, repo_tree)
        assert "src/components/Button.tsx" in paths
        assert "src/components/Button/index.tsx" in paths

    def test_unknown_extension_returns_empty(self):
        diff = "+some markdown content"
        repo_tree = ["README.md"]
        paths = resolve_imports("README.md", diff, repo_tree)
        assert paths == []

    def test_no_imports_returns_empty(self):
        diff = "+x = 1\n+y = 2"
        repo_tree = ["src/app.py"]
        paths = resolve_imports("src/app.py", diff, repo_tree)
        assert paths == []

    def test_deduplication(self):
        """Same import twice should not produce duplicate paths."""
        diff = "+from utils import helper\n+from utils import formatter"
        repo_tree = [
            "src/utils.py",
            "src/utils/__init__.py",
        ]
        paths = resolve_imports("src/app.py", diff, repo_tree)
        # Should deduplicate
        assert len(paths) == len(set(paths))
