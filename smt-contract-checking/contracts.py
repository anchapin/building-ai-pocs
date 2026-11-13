"""Contract decorators for the SMT-contract-checking slice.

Backend resolution order: ``deal`` -> ``icontract`` -> a local fallback.

Why the fallback exists
-----------------------
``crosshair check`` reads contracts written with ``deal`` or ``icontract``;
those are the two libraries the issue names.  This sandbox has no PyPI access
(see REPORT.md, "Environment"), so neither library could be installed and the
slice still has to be importable, testable and contract-checkable offline.
The fallback below implements the *same* semantics (a precondition predicate
over the arguments, a postcondition predicate over ``result`` and the
arguments) with the standard library only, so that:

* the example tests run anywhere,
* ``tools/grid_search.py`` can evaluate the contracts offline,
* and, once ``deal`` or ``icontract`` is installed, the *real* library
  decorators are used instead and the fallback is never exercised (the
  slice source does not change).

Contract semantics used by the fallback (and by both real libraries):

* ``pre(predicate)`` -- ``predicate(<all arguments>)`` must hold; the call
  raises ``ContractViolation`` otherwise.
* ``ensure(predicate)`` -- ``predicate(result, <all arguments>)`` must hold
  after the call; the call raises ``ContractViolation`` otherwise.

The predicates are plain lambdas whose parameters are matched *by name*
against the decorated function's arguments, so the same lambda text works
under ``deal`` (which passes positionally, in the function's own order) and
under ``icontract`` (which passes by name).
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Dict, List, Tuple

__all__ = [
    "BACKEND",
    "ContractViolation",
    "pre",
    "ensure",
    "contract_conditions",
    "evaluate_contracts",
    "predicate_holds",
    "unwrap",
]


class ContractViolation(AssertionError):
    """Raised by the local fallback when a contract is violated."""


# --------------------------------------------------------------------------
# Backend resolution
# --------------------------------------------------------------------------

BACKEND = "local"

try:  # pragma: no cover - depends on the environment
    from deal import ensure as _deal_ensure  # type: ignore
    from deal import pre as _deal_pre  # type: ignore

    BACKEND = "deal"
except Exception:  # pragma: no cover - depends on the environment
    try:
        from icontract import ensure as _icontract_ensure  # type: ignore
        from icontract import pre as _icontract_pre  # type: ignore

        BACKEND = "icontract"
    except Exception:  # pragma: no cover - depends on the environment
        _icontract_ensure = None
        _icontract_pre = None


# --------------------------------------------------------------------------
# Local fallback implementation
# --------------------------------------------------------------------------


def _bind(fn: Callable[..., Any], args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Bind call arguments to the decorated function's parameter names."""
    bound = inspect.signature(fn).bind(*args, **kwargs)
    bound.apply_defaults()
    return dict(bound.arguments)


def _eval_condition(
    predicate: Callable[..., Any],
    data: Dict[str, Any],
    result: Any = None,
    has_result: bool = False,
) -> bool:
    """Evaluate a contract predicate, matching parameters by name."""
    kwargs: Dict[str, Any] = {}
    for name in _predicate_params(predicate):
        if name == "result" and has_result:
            kwargs[name] = result
        elif name in data:
            kwargs[name] = data[name]
        else:
            raise ContractViolation(
                f"contract predicate {predicate!r} asks for unknown argument {name!r}"
            )
    return bool(predicate(**kwargs))


@functools.lru_cache(maxsize=None)
def _predicate_params(predicate: Callable[..., Any]) -> Tuple[str, ...]:
    """Parameter names of a contract predicate (cached: the search is hot)."""
    return tuple(inspect.signature(predicate).parameters)


def predicate_holds(
    predicate: Callable[..., Any],
    data: Dict[str, Any],
    result: Any = None,
    has_result: bool = False,
) -> bool:
    """Public wrapper around the predicate evaluation used by the fallback."""
    return _eval_condition(predicate, data, result=result, has_result=has_result)


def _make_wrapper(
    fn: Callable[..., Any],
    own_pre: List[Callable[..., Any]],
    own_post: List[Callable[..., Any]],
) -> Callable[..., Any]:
    """Wrap ``fn`` so that the attached contracts are enforced at runtime."""
    inherited_pre = list(getattr(fn, "_preconditions", []))
    inherited_post = list(getattr(fn, "_postconditions", []))

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        data = _bind(fn, args, kwargs)
        for predicate in inherited_pre + own_pre:
            if not _eval_condition(predicate, data):
                raise ContractViolation(
                    f"precondition {predicate!r} of {fn.__name__} failed for {data!r}"
                )
        result = fn(*args, **kwargs)
        for predicate in inherited_post + own_post:
            if not _eval_condition(predicate, data, result=result, has_result=True):
                raise ContractViolation(
                    f"postcondition {predicate!r} of {fn.__name__} failed for "
                    f"{data!r} -> {result!r}"
                )
        return result

    wrapper._preconditions = inherited_pre + own_pre  # type: ignore[attr-defined]
    wrapper._postconditions = inherited_post + own_post  # type: ignore[attr-defined]
    wrapper._contract_target = fn  # type: ignore[attr-defined]
    return wrapper


if BACKEND == "deal":  # pragma: no cover - depends on the environment
    pre = _deal_pre
    ensure = _deal_ensure
elif BACKEND == "icontract":  # pragma: no cover - depends on the environment
    pre = _icontract_pre
    ensure = _icontract_ensure
else:

    def pre(condition: Callable[..., Any]) -> Callable[..., Any]:
        """Attach a precondition predicate (fallback implementation)."""

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            return _make_wrapper(fn, [condition], [])

        return decorate

    def ensure(condition: Callable[..., Any]) -> Callable[..., Any]:
        """Attach a postcondition predicate (fallback implementation)."""

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            return _make_wrapper(fn, [], [condition])

        return decorate


def contract_conditions(fn: Callable[..., Any]) -> Tuple[List[Callable[..., Any]], List[Callable[..., Any]]]:
    """Return ``(preconditions, postconditions)`` attached to ``fn``.

    Works for the fallback (attributes set by ``_make_wrapper``) and for
    ``deal``/``icontract`` (whose decorators store the predicates on the
    wrapped function under their own attribute names).
    """
    pre_conditions = list(getattr(fn, "_preconditions", []) or [])
    post_conditions = list(getattr(fn, "_postconditions", []) or [])

    deal_pre = getattr(fn, "__preconditions__", None)
    if deal_pre:  # pragma: no cover - depends on the environment
        pre_conditions.extend(deal_pre)
    deal_post = getattr(fn, "__postconditions__", None)
    if deal_post:  # pragma: no cover - depends on the environment
        post_conditions.extend(deal_post)

    icontract_pre = getattr(fn, "__precondition__", None)
    if icontract_pre is not None:  # pragma: no cover - depends on the environment
        pre_conditions.append(icontract_pre)
    icontract_post = getattr(fn, "__postcondition__", None)
    if icontract_post is not None:  # pragma: no cover - depends on the environment
        post_conditions.append(icontract_post)

    for attr in ("_preconditions", "__preconditions__", "preconditions"):
        extra = getattr(fn, attr, None)
        if extra:
            pre_conditions.extend(list(extra))
    for attr in ("_postconditions", "__postconditions__", "postconditions"):
        extra = getattr(fn, attr, None)
        if extra:
            post_conditions.extend(list(extra))

    # de-duplicate, preserving order (the fallback attributes are read twice)
    def _unique(items: List[Callable[..., Any]]) -> List[Callable[..., Any]]:
        seen: List[int] = []
        out: List[Callable[..., Any]] = []
        for item in items:
            if id(item) not in seen:
                seen.append(id(item))
                out.append(item)
        return out

    return _unique(pre_conditions), _unique(post_conditions)


def unwrap(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Return the undecorated function behind the contract decorators.

    The decorators stack (``@ensure`` on top of ``@pre``), so the chain is
    followed to the bottom.
    """
    seen = 0
    while seen < 16:
        target = getattr(fn, "_contract_target", None)
        if target is None:
            break
        fn = target
        seen += 1
    return getattr(fn, "__wrapped__", fn)


def evaluate_contracts(
    fn: Callable[..., Any], kwargs: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate a function's contracts *without* runtime enforcement.

    Returns a dict with:

    * ``result``      -- the value of the undecorated function (``None`` when
      a precondition failed and the call was therefore not made),
    * ``pre_ok``      -- every precondition held,
    * ``post_ok``     -- every postcondition held,
    * ``violated``    -- list of ``(kind, predicate)`` for the failures.

    This is what the offline search tool uses: it lets the tool evaluate a
    contract on an input *and* still see the value the function returned.
    """
    pre_conditions, post_conditions = contract_conditions(fn)
    data = dict(kwargs)
    violated: List[Tuple[str, Callable[..., Any]]] = []

    for predicate in pre_conditions:
        if not predicate_holds(predicate, data):
            violated.append(("precondition", predicate))
    if violated:
        return {
            "result": None,
            "pre_ok": False,
            "post_ok": True,
            "violated": violated,
        }

    result = unwrap(fn)(**kwargs)
    for predicate in post_conditions:
        if not predicate_holds(predicate, data, result=result, has_result=True):
            violated.append(("postcondition", predicate))
    return {
        "result": result,
        "pre_ok": True,
        "post_ok": not any(kind == "postcondition" for kind, _ in violated),
        "violated": violated,
    }
