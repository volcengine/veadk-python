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

"""Repo-wide guard: no outbound HTTP call may omit an explicit timeout.

`requests` has no default timeout. A call without one blocks forever if the
peer accepts the connection and then goes quiet, which stalls the whole
process for the synchronous tools ADK invokes inline on the event loop. The
timeout sweep already fixed every call site; this test keeps them fixed.

The checker is deliberately narrow, because a noisy guard gets deleted:

* the receiver must be the `requests` module itself, a local name that was
  bound to `requests.Session()` in an enclosing scope, or an attribute that
  was bound to one in the same class (`self._session = requests.Session()`
  in `__init__`, then `self._session.request(...)` from any method);
* `session.get("state")` on a dict, `db.session.delete(post)` on SQLAlchemy,
  and every other `.get`/`.delete` on an unrelated object are ignored;
* a `**kwargs` splat counts as "has a timeout" -- it cannot be disproved.

One shape stays out of reach on purpose: a session inherited from a base class
in another module (`VikingDBMemoryClient(Service)` gets its `self.session` from
the volcengine SDK) has no binding to find in the file being parsed, and
trusting every `self.session.get(...)` without one would flag dicts.

Unparseable files are skipped loudly: the set of files that fail to parse must
match `_EXPECTED_UNPARSEABLE` exactly, so a newly broken file fails this test
instead of silently shrinking its coverage.
"""

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_ROOT = _REPO_ROOT / "veadk"

# `requests` verbs plus `request()` itself. `timeout` is keyword-only in every
# one of these signatures, so a keyword scan is sufficient.
_HTTP_METHODS = frozenset(
    {"get", "post", "put", "delete", "patch", "head", "options", "request"}
)

# Known-broken sources that predate this test. Anything else that fails to
# parse is a regression, not a skip.
_EXPECTED_UNPARSEABLE = frozenset(
    {
        "veadk/integrations/ve_faas/template/"
        "{{cookiecutter.local_dir_name}}/src/agent.py",
    }
)

# Real files in this repo that call `.get`/`.delete` on something that is not a
# `requests` session. They must stay green.
_KNOWN_FALSE_POSITIVE_FILES = (
    "veadk/cli/cli_frontend.py",
    "veadk/integrations/agentkit/evaluation/feedback.py",
    "veadk/integrations/ve_faas/web_template/"
    "{{cookiecutter.local_dir_name}}/src/app.py",
)

# Real file that keeps its session on an attribute (`self._session`, bound in
# `GitHubClient.__init__` and used from `_request`). It passes a timeout today,
# so the scan above is green either way -- `test_attribute_session_file_is_...`
# below is what proves it is green for the right reason.
_REAL_ATTRIBUTE_SESSION_FILE = "veadk/cli/github_cicd.py"

_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _is_requests_session_call(node: ast.AST | None) -> bool:
    """True for the expression `requests.Session(...)`."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Session"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "requests"
    )


def _binds_a_requests_session(node: ast.AST | None) -> bool:
    """True for any expression that can evaluate to a `requests.Session()`.

    `session or requests.Session()` is the standard injectable-client idiom
    (`GitHubClient.__init__`), and it hides the constructor inside a `BoolOp`.
    """
    if _is_requests_session_call(node):
        return True
    if isinstance(node, ast.BoolOp):
        return any(_binds_a_requests_session(value) for value in node.values)
    if isinstance(node, ast.IfExp):
        return _binds_a_requests_session(node.body) or _binds_a_requests_session(
            node.orelse
        )
    return False


def _attribute_path(node: ast.AST) -> str | None:
    """Dotted path for a plain attribute chain: `self._session` -> "self._session".

    Returns None for anything with a computed base (`clients[0].session`), which
    cannot be matched against a binding by name.
    """
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not parts or not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _iter_own_scope(node: ast.AST):
    """Yield descendants of `node` without descending into nested scopes."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPE_NODES):
            continue
        yield child
        yield from _iter_own_scope(child)


def _session_binding_targets(node: ast.AST) -> list[ast.expr]:
    """Assignment targets that `node` binds to a `requests.Session()`."""
    if isinstance(node, ast.Assign) and _binds_a_requests_session(node.value):
        return node.targets
    if isinstance(node, ast.AnnAssign) and _binds_a_requests_session(node.value):
        return [node.target]
    if isinstance(node, ast.withitem) and _binds_a_requests_session(node.context_expr):
        return [node.optional_vars] if node.optional_vars else []
    return []


def _session_names_in_scope(scope: ast.AST) -> set[str]:
    """Local names bound to `requests.Session()` directly inside `scope`."""
    names: set[str] = set()
    for node in _iter_own_scope(scope):
        names.update(
            target.id
            for target in _session_binding_targets(node)
            if isinstance(target, ast.Name)
        )
    return names


def _session_attributes_in_scope(scope: ast.AST) -> set[str]:
    """Dotted attribute paths bound to `requests.Session()` inside `scope`.

    A class body is walked in full, nested scopes included: the binding lives in
    `__init__` and every use lives in a sibling method, so anything narrower
    would miss the only shape this pattern takes. Bare names are deliberately
    *not* collected that way -- `self._session` is qualified by its owner, a
    local `session` is not, and leaking locals between sibling methods is
    exactly what turns a guard noisy enough to get deleted.
    """
    walker = (
        ast.walk(scope) if isinstance(scope, ast.ClassDef) else _iter_own_scope(scope)
    )
    paths: set[str] = set()
    for node in walker:
        for target in _session_binding_targets(node):
            path = _attribute_path(target)
            if path is not None:
                paths.add(path)
    return paths


def _call_has_timeout(node: ast.Call) -> bool:
    for keyword in node.keywords:
        # `keyword.arg is None` is a `**kwargs` splat: the timeout may well be
        # in there, so give the call the benefit of the doubt.
        if keyword.arg in ("timeout", None):
            return True
    return False


class _UnboundedHttpCallFinder(ast.NodeVisitor):
    """Collect line numbers of `requests` calls that carry no `timeout=`."""

    def __init__(self) -> None:
        self.offender_lines: list[int] = []
        # Stack of session receivers visible in the current scope: bare local
        # names plus dotted attribute paths such as `self._session`.
        self._session_targets: list[set[str]] = []

    def _visit_scope(self, node: ast.AST) -> None:
        inherited = set(self._session_targets[-1]) if self._session_targets else set()
        self._session_targets.append(
            inherited
            | _session_names_in_scope(node)
            | _session_attributes_in_scope(node)
        )
        try:
            self.generic_visit(node)
        finally:
            self._session_targets.pop()

    visit_Module = _visit_scope
    visit_FunctionDef = _visit_scope
    visit_AsyncFunctionDef = _visit_scope
    visit_ClassDef = _visit_scope
    visit_Lambda = _visit_scope

    def _is_tracked(self, target: str) -> bool:
        return bool(self._session_targets) and target in self._session_targets[-1]

    def _is_http_call(self, node: ast.Call) -> bool:
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _HTTP_METHODS:
            return False
        receiver = func.value
        if isinstance(receiver, ast.Name):
            return receiver.id == "requests" or self._is_tracked(receiver.id)
        if isinstance(receiver, ast.Attribute):
            path = _attribute_path(receiver)
            return path is not None and self._is_tracked(path)
        # `requests.Session().get(...)` without an intermediate name.
        return _binds_a_requests_session(receiver)

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_http_call(node) and not _call_has_timeout(node):
            self.offender_lines.append(node.lineno)
        self.generic_visit(node)


def find_unbounded_http_calls(source: str) -> list[int]:
    """Line numbers of timeout-less `requests` calls in `source`."""
    finder = _UnboundedHttpCallFinder()
    finder.visit(ast.parse(source))
    return sorted(finder.offender_lines)


def _iter_package_files() -> list[Path]:
    return sorted(_PACKAGE_ROOT.rglob("*.py"))


def _scan_package() -> tuple[list[str], set[str]]:
    """Return (offenders as `path:line`, relative paths that failed to parse)."""
    offenders: list[str] = []
    unparseable: set[str] = set()
    for path in _iter_package_files():
        relative = path.relative_to(_REPO_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            unparseable.add(relative)
            continue
        finder = _UnboundedHttpCallFinder()
        finder.visit(tree)
        offenders.extend(f"{relative}:{line}" for line in sorted(finder.offender_lines))
    return offenders, unparseable


def test_package_has_python_files_to_scan():
    # Cheap tripwire: a broken path would make every other assertion vacuous.
    assert len(_iter_package_files()) > 100


def test_no_unbounded_http_calls_under_veadk():
    offenders, _ = _scan_package()

    assert not offenders, (
        "Outbound HTTP call(s) without an explicit `timeout=`; `requests` has "
        "no default timeout, so these can block forever. Pass "
        "`DEFAULT_HTTP_TIMEOUT` (or an explicit per-call value for bulk "
        "transfers) from `veadk.utils.http_defaults`:\n  " + "\n  ".join(offenders)
    )


def test_unparseable_files_match_the_allowlist():
    _, unparseable = _scan_package()

    assert unparseable == set(_EXPECTED_UNPARSEABLE), (
        "The set of files this guard cannot parse changed, so its coverage "
        "changed too. Newly unparseable: "
        f"{sorted(unparseable - set(_EXPECTED_UNPARSEABLE))}; no longer "
        f"unparseable (drop from the allowlist): "
        f"{sorted(set(_EXPECTED_UNPARSEABLE) - unparseable)}"
    )


@pytest.mark.parametrize("relative_path", _KNOWN_FALSE_POSITIVE_FILES)
def test_known_false_positive_files_stay_green(relative_path):
    path = _REPO_ROOT / relative_path
    assert path.is_file(), f"missing fixture file: {relative_path}"

    assert find_unbounded_http_calls(path.read_text(encoding="utf-8")) == []


def _strip_timeout_evidence(tree: ast.AST) -> ast.AST:
    """Remove everything that makes a call look bounded, keeping line numbers.

    That means `timeout=` and also `**kwargs`, which `_call_has_timeout` gives
    the benefit of the doubt. `GitHubClient._request` forwards a splat, so
    dropping only `timeout=` would leave it green through the splat rule and
    the assertion below would prove nothing about the receiver.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            node.keywords = [
                kw for kw in node.keywords if kw.arg not in ("timeout", None)
            ]
    return tree


def test_attribute_session_file_is_green_for_the_right_reason():
    """The real `self._session` call site must be *seen*, not merely bounded.

    Asserting the file is clean proves nothing on its own: it was clean before
    the checker could resolve attribute-held sessions at all. So take the same
    file, remove what marks its calls as bounded, and require the checker to
    flag exactly the calls made on `self._session`.
    """
    path = _REPO_ROOT / _REAL_ATTRIBUTE_SESSION_FILE
    tree = ast.parse(path.read_text(encoding="utf-8"))

    expected = sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _HTTP_METHODS
        and _attribute_path(node.func.value) == "self._session"
    )
    assert expected, (
        f"{_REAL_ATTRIBUTE_SESSION_FILE} no longer holds a session on "
        "`self._session`; point this test at a file that does"
    )

    finder = _UnboundedHttpCallFinder()
    finder.visit(tree)
    assert finder.offender_lines == [], "fixture file must be clean as committed"

    finder = _UnboundedHttpCallFinder()
    finder.visit(_strip_timeout_evidence(tree))
    assert sorted(finder.offender_lines) == expected


@pytest.mark.parametrize(
    "source",
    [
        "import requests\nrequests.get(url)\n",
        "import requests\nrequests.post(url, json=payload)\n",
        "import requests\nrequests.put(url, data=body)\n",
        "import requests\nrequests.delete(url)\n",
        "import requests\nrequests.patch(url, json=payload)\n",
        "import requests\nrequests.head(url)\n",
        "import requests\nrequests.request('GET', url)\n",
    ],
)
def test_checker_flags_module_level_calls_without_timeout(source):
    assert find_unbounded_http_calls(source) == [2]


def test_checker_accepts_module_level_calls_with_timeout():
    source = (
        "import requests\n"
        "requests.get(url, timeout=(10.0, 60.0))\n"
        "requests.post(url, json=payload, timeout=30)\n"
    )

    assert find_unbounded_http_calls(source) == []


def test_checker_flags_session_calls_without_timeout():
    source = (
        "import requests\n"
        "def fetch(url):\n"
        "    session = requests.Session()\n"
        "    return session.post(url, json={})\n"
    )

    assert find_unbounded_http_calls(source) == [4]


def test_checker_accepts_session_calls_with_timeout():
    source = (
        "import requests\n"
        "def fetch(url):\n"
        "    session = requests.Session()\n"
        "    return session.post(url, json={}, timeout=(10.0, 300.0))\n"
    )

    assert find_unbounded_http_calls(source) == []


def test_checker_flags_attribute_session_calls_without_timeout():
    source = (
        "import requests\n"
        "class Client:\n"
        "    def __init__(self):\n"
        "        self._session = requests.Session()\n"
        "    def fetch(self, url):\n"
        "        return self._session.request('GET', url)\n"
    )

    assert find_unbounded_http_calls(source) == [6]


def test_checker_accepts_attribute_session_calls_with_timeout():
    source = (
        "import requests\n"
        "class Client:\n"
        "    def __init__(self):\n"
        "        self._session = requests.Session()\n"
        "    def fetch(self, url):\n"
        "        return self._session.request('GET', url, timeout=30)\n"
    )

    assert find_unbounded_http_calls(source) == []


def test_checker_sees_through_the_injectable_session_idiom():
    """`session or requests.Session()` still binds a session."""
    source = (
        "import requests\n"
        "class Client:\n"
        "    def __init__(self, session=None):\n"
        "        self._session = session or requests.Session()\n"
        "    def fetch(self, url):\n"
        "        return self._session.get(url)\n"
    )

    assert find_unbounded_http_calls(source) == [6]


def test_attribute_sessions_do_not_leak_across_classes():
    """A `self._session` in one class says nothing about another's."""
    source = (
        "import requests\n"
        "class Http:\n"
        "    def __init__(self):\n"
        "        self._session = requests.Session()\n"
        "class Store:\n"
        "    def __init__(self, cache):\n"
        "        self._session = cache\n"
        "    def read(self, key):\n"
        "        return self._session.get(key)\n"
    )

    assert find_unbounded_http_calls(source) == []


def test_checker_tracks_attribute_sessions_bound_outside_a_class():
    source = (
        "import requests\n"
        "def configure(client):\n"
        "    client.session = requests.Session()\n"
        "    return client.session.post(url)\n"
    )

    assert find_unbounded_http_calls(source) == [4]


def test_checker_tracks_sessions_opened_in_a_with_block():
    source = (
        "import requests\n"
        "def fetch(url):\n"
        "    with requests.Session() as s:\n"
        "        return s.get(url)\n"
    )

    assert find_unbounded_http_calls(source) == [4]


def test_checker_tracks_sessions_through_nested_functions():
    source = (
        "import requests\n"
        "def outer(url):\n"
        "    session = requests.Session()\n"
        "    def inner():\n"
        "        return session.get(url)\n"
        "    return inner()\n"
    )

    assert find_unbounded_http_calls(source) == [5]


def test_checker_flags_inline_session_calls():
    source = "import requests\nrequests.Session().get(url)\n"

    assert find_unbounded_http_calls(source) == [2]


def test_session_names_do_not_leak_across_functions():
    source = (
        "import requests\n"
        "def a(url):\n"
        "    session = requests.Session()\n"
        "    return session.get(url, timeout=5)\n"
        "def b(session):\n"
        "    return session.get('events')\n"
    )

    assert find_unbounded_http_calls(source) == []


@pytest.mark.parametrize(
    "source",
    [
        # Flask/Werkzeug session dict.
        "def view():\n    if not session.get('admin_logged_in'):\n        return 401\n",
        # Plain dict payloads.
        "def read(session):\n    return session.get('state')\n",
        "def read(session):\n    return session.get('events')\n",
        # SQLAlchemy.
        "def drop(post):\n    db.session.delete(post)\n",
        "def load(model, pk):\n    return db.session.get(model, pk)\n",
        # Similarly named locals that are not requests sessions.
        "import requests\ndef f(url):\n    s = build()\n    return s.get(url)\n",
        # A module named like `requests` but not it.
        "def f(call_id):\n    return auth_requests.get(call_id)\n",
        "def f(self, rid):\n    return self._pending_requests.get(rid)\n",
        # An attribute session with no binding in this file: inherited from a
        # base class elsewhere, or just a dict on `self`.
        "class C:\n    def f(self, url):\n        return self.session.get(url)\n",
        # A computed base cannot be matched against a binding by name.
        "import requests\n"
        "def f(clients, url):\n"
        "    clients[0].session = requests.Session()\n"
        "    return clients[0].session.get(url)\n",
        # Non-HTTP attribute on the real module.
        "import requests\nrequests.Session()\n",
    ],
)
def test_checker_ignores_non_requests_receivers(source):
    assert find_unbounded_http_calls(source) == []


def test_checker_treats_kwargs_splat_as_bounded():
    source = (
        "import requests\n"
        "def fetch(url, **kwargs):\n"
        "    return requests.get(url, **kwargs)\n"
    )

    assert find_unbounded_http_calls(source) == []


def test_checker_reports_every_offender_in_a_file():
    source = (
        "import requests\n"
        "def a(url):\n"
        "    return requests.get(url)\n"
        "def b(url):\n"
        "    session = requests.Session()\n"
        "    return session.post(url, timeout=1)\n"
        "def c(url):\n"
        "    return requests.request('POST', url)\n"
    )

    assert find_unbounded_http_calls(source) == [3, 8]


def test_failure_message_names_file_and_line(tmp_path):
    # End-to-end shape check on the message the guard would print: it must
    # point at `file:line` so the fix is obvious.
    offender = tmp_path / "broken.py"
    offender.write_text("import requests\nrequests.get(url)\n", encoding="utf-8")

    lines = find_unbounded_http_calls(offender.read_text(encoding="utf-8"))
    rendered = [f"{offender.name}:{line}" for line in lines]

    assert rendered == ["broken.py:2"]
