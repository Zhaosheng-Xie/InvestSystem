"""Pinned decimal arithmetic for deterministic synthetic Stage 5 evaluation."""

from __future__ import annotations

from collections.abc import Callable
from decimal import ROUND_HALF_EVEN, Context, localcontext
from functools import wraps

STAGE5_DECIMAL_CONTEXT_ID = "stage5-decimal-p50-half-even-v1"
STAGE5_DECIMAL_CONTEXT = Context(
    prec=50,
    rounding=ROUND_HALF_EVEN,
    Emin=-999_999,
    Emax=999_999,
    capitals=1,
    clamp=0,
)


def with_stage5_decimal_context[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    """Run a pure evaluator under the Stage 5 pinned Decimal context."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        with localcontext(STAGE5_DECIMAL_CONTEXT):
            return function(*args, **kwargs)

    return wrapped
