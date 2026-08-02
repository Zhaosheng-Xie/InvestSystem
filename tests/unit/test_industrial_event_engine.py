from __future__ import annotations

import pytest

from invest_system.strategies.industrial_event import (
    MinimumObligationKind,
    resolve_contract_effectiveness,
    resolve_economic_closure,
)


@pytest.mark.parametrize(
    ("contract_effective", "conditions_satisfied", "expected"),
    (
        (True, True, True),
        (True, False, True),
        (True, None, True),
        (False, True, True),
        (False, False, False),
        (False, None, None),
        (None, True, True),
        (None, False, None),
        (None, None, None),
    ),
)
def test_contract_effectiveness_uses_approved_three_valued_or(
    contract_effective: bool | None,
    conditions_satisfied: bool | None,
    expected: bool | None,
) -> None:
    assert resolve_contract_effectiveness(contract_effective, conditions_satisfied) is expected


@pytest.mark.parametrize("invalid", (0, 1, "true"))
def test_contract_effectiveness_rejects_non_boolean_values(invalid: object) -> None:
    with pytest.raises(TypeError):
        resolve_contract_effectiveness(invalid, False)  # type: ignore[arg-type]


def _economic_closure(
    *,
    signed: bool | None = True,
    effective: bool | None = True,
    conditions_satisfied: bool | None = False,
    binding: bool | None = True,
    kind: MinimumObligationKind | None = MinimumObligationKind.AMOUNT,
    cancellation_can_zero: bool | None = False,
    return_can_zero: bool | None = False,
) -> bool | None:
    return resolve_economic_closure(
        contract_signed_or_formally_ordered=signed,
        contract_effective=effective,
        material_conditions_satisfied=conditions_satisfied,
        binding_minimum_obligation=binding,
        minimum_obligation_kind=kind,
        cancellation_can_zero_minimum=cancellation_can_zero,
        return_or_acceptance_can_zero_minimum=return_can_zero,
    )


def test_economic_closure_is_true_only_when_every_required_link_is_closed() -> None:
    assert _economic_closure() is True


def test_economic_closure_is_unknown_when_no_link_is_open_but_one_is_unknown() -> None:
    assert _economic_closure(signed=None) is None


def test_economic_closure_known_false_takes_precedence_over_an_unknown_link() -> None:
    assert _economic_closure(signed=False, cancellation_can_zero=None) is False


def test_economic_closure_requires_minimum_obligation_kind_when_binding_is_true() -> None:
    assert _economic_closure(binding=True, kind=None) is None


def test_economic_closure_rejects_invalid_field_types() -> None:
    with pytest.raises(TypeError):
        _economic_closure(signed=1)  # type: ignore[arg-type]
