# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Cold-start entrypoint for the Studio server without the general CLI."""

from __future__ import annotations

import ast
import importlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Any


_STUDIO_LAZY_ADK_PACKAGES = "_VEADK_STUDIO_LAZY_ADK_PACKAGES"


def _install_lazy_package(
    name: str,
    exports: dict[str, tuple[str, str | None]],
) -> ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.find_spec(name)
    if spec is None or spec.submodule_search_locations is None:
        raise ImportError(f"Unable to locate package {name!r}")
    package = ModuleType(name)
    package.__file__ = spec.origin
    package.__loader__ = spec.loader
    package.__package__ = name
    package.__path__ = list(spec.submodule_search_locations)
    package.__spec__ = spec
    package.__dict__["__all__"] = list(exports)

    def _load_export(attribute: str) -> Any:
        target = exports.get(attribute)
        if target is None:
            raise AttributeError(f"module {name!r} has no attribute {attribute!r}")
        module_name, target_attribute = target
        module = importlib.import_module(module_name)
        value = (
            module if target_attribute is None else getattr(module, target_attribute)
        )
        setattr(package, attribute, value)
        return value

    package.__getattr__ = _load_export  # type: ignore[attr-defined]
    sys.modules[name] = package
    return package


def _install_lazy_module(name: str, eager: dict[str, Any]) -> ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    parent_name, _, _child = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    parent_path = getattr(parent, "__path__", None)
    if parent is None or parent_path is None:
        raise ImportError(f"Unable to locate parent package {parent_name!r}")
    spec = importlib.machinery.PathFinder.find_spec(name, parent_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to locate module {name!r}")
    loader = spec.loader
    proxy = ModuleType(name)
    proxy.__file__ = spec.origin
    proxy.__loader__ = spec.loader
    proxy.__package__ = parent_name
    proxy.__spec__ = spec
    proxy.__dict__.update(eager)
    loaded: list[ModuleType] = []

    def _load_real() -> ModuleType:
        if loaded:
            return loaded[0]
        real = importlib.util.module_from_spec(spec)
        sys.modules[name] = real
        try:
            loader.exec_module(real)
        except BaseException:
            sys.modules[name] = proxy
            raise
        loaded.append(real)
        return real

    def _load_attribute(attribute: str) -> Any:
        if attribute.startswith("__"):
            raise AttributeError(f"module {name!r} has no attribute {attribute!r}")
        return getattr(_load_real(), attribute)

    proxy.__getattr__ = _load_attribute  # type: ignore[attr-defined]
    proxy.__dict__["_load_real_module"] = _load_real
    sys.modules[name] = proxy
    return proxy


def _literal_assignment(module_name: str, assignment: str) -> Any:
    parent_name, _, _child = module_name.rpartition(".")
    parent = sys.modules.get(parent_name)
    parent_path = getattr(parent, "__path__", None)
    if parent is None or parent_path is None:
        raise ImportError(f"Unable to locate parent package {parent_name!r}")
    spec = importlib.machinery.PathFinder.find_spec(module_name, parent_path)
    if spec is None or spec.origin is None:
        raise ImportError(f"Unable to locate module {module_name!r}")
    source = Path(spec.origin).read_text(encoding="utf-8")
    for node in ast.parse(source, filename=spec.origin).body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if node.value is not None and any(
            isinstance(target, ast.Name) and target.id == assignment
            for target in targets
        ):
            return ast.literal_eval(node.value)
    raise ImportError(f"Unable to locate {assignment!r} in {module_name!r}")


def _install_studio_adk_imports() -> None:
    """Keep command-only ADK exports out of the Studio readiness path."""

    _install_lazy_package(
        "google.adk",
        {
            "version": ("google.adk.version", None),
            "__version__": ("google.adk.version", "__version__"),
            "Agent": ("google.adk.agents.llm_agent", "Agent"),
            "Context": ("google.adk.agents.context", "Context"),
            "Event": ("google.adk.events.event", "Event"),
            "Runner": ("google.adk.runners", "Runner"),
            "Workflow": ("google.adk.workflow", "Workflow"),
        },
    )
    _install_lazy_package(
        "google.adk.cli",
        {"main": ("google.adk.cli.cli_tools_click", "main")},
    )
    _install_lazy_package(
        "google.adk.workflow",
        {
            "BaseNode": ("google.adk.workflow._base_node", "BaseNode"),
            "DEFAULT_ROUTE": ("google.adk.workflow._graph", "DEFAULT_ROUTE"),
            "Edge": ("google.adk.workflow._graph", "Edge"),
            "FunctionNode": (
                "google.adk.workflow._function_node",
                "FunctionNode",
            ),
            "JoinNode": ("google.adk.workflow._join_node", "JoinNode"),
            "Node": ("google.adk.workflow._node", "Node"),
            "NodeTimeoutError": (
                "google.adk.workflow._errors",
                "NodeTimeoutError",
            ),
            "RetryConfig": (
                "google.adk.workflow._retry_config",
                "RetryConfig",
            ),
            "START": ("google.adk.workflow._base_node", "START"),
            "Workflow": ("google.adk.workflow._workflow", "Workflow"),
            "node": ("google.adk.workflow._node", "node"),
        },
    )
    _install_lazy_module(
        "google.adk.cli.cli_eval",
        {"EVAL_SESSION_ID_PREFIX": "___eval___session___"},
    )
    _install_lazy_module(
        "google.adk.cli.cli_deploy",
        {
            "_AGENT_ENGINE_CLASS_METHODS": _literal_assignment(
                "google.adk.cli.cli_deploy",
                "_AGENT_ENGINE_CLASS_METHODS",
            )
        },
    )
    dev_server = _install_lazy_module("google.adk.cli.dev_server", {})

    class _DeferredDevServer:
        def __new__(cls, *args: Any, **kwargs: Any) -> Any:
            real = dev_server.__dict__["_load_real_module"]()
            return real.DevServer(*args, **kwargs)

    setattr(dev_server, "DevServer", _DeferredDevServer)
    os.environ[_STUDIO_LAZY_ADK_PACKAGES] = "1"


class _DeferredEvalManager:
    def __init__(
        self,
        module_name: str,
        class_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._module_name = module_name
        self._class_name = class_name
        self._args = args
        self._kwargs = kwargs
        self._delegate: Any | None = None

    def _resolve(self) -> Any:
        if self._delegate is None:
            manager = getattr(
                importlib.import_module(self._module_name), self._class_name
            )
            self._delegate = manager(*self._args, **self._kwargs)
        return self._delegate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)


def studio_fast_api_factory() -> Any:
    """Return ADK's production app factory with evaluation storage deferred."""

    fast_api = importlib.import_module("google.adk.cli.fast_api")

    class _DeferredEvalSetsManager(_DeferredEvalManager):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(
                "google.adk.evaluation.local_eval_sets_manager",
                "LocalEvalSetsManager",
                *args,
                **kwargs,
            )

    class _DeferredEvalSetResultsManager(_DeferredEvalManager):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(
                "google.adk.evaluation.local_eval_set_results_manager",
                "LocalEvalSetResultsManager",
                *args,
                **kwargs,
            )

    setattr(fast_api, "LocalEvalSetsManager", _DeferredEvalSetsManager)
    setattr(
        fast_api,
        "LocalEvalSetResultsManager",
        _DeferredEvalSetResultsManager,
    )
    return fast_api.get_fast_api_app


def _bootstrap_provider() -> None:
    provider = (
        os.environ.get("AGENTKIT_CLOUD_PROVIDER")
        or os.environ.get("CLOUD_PROVIDER")
        or "volcengine"
    )
    arguments = sys.argv[1:]
    for index, argument in enumerate(arguments):
        if argument.startswith("--provider="):
            provider = argument.partition("=")[2]
            break
        if argument == "--provider" and index + 1 < len(arguments):
            provider = arguments[index + 1]
            break
    provider = provider.strip().lower()
    if provider == "volces":
        provider = "volcengine"
    if provider not in {"volcengine", "byteplus"}:
        return
    os.environ["AGENTKIT_CLOUD_PROVIDER"] = provider
    os.environ["CLOUD_PROVIDER"] = provider


_bootstrap_provider()
_install_studio_adk_imports()

from veadk.cli.cli_frontend import studio  # noqa: E402


def main() -> None:
    """Run only the Studio Click command tree."""
    studio(prog_name="studio")


if __name__ == "__main__":
    main()
