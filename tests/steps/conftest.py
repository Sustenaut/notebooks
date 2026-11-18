"""The suite's own steps that more than one feature uses: the checks pubtest has no step for yet."""

from __future__ import annotations

import pytest
from pubtest.core import dig, same
from pytest_bdd import parsers, then


@then(parsers.re(r'the result\'s "(?P<key>[^"]+)" is about "(?P<wanted>[^"]+)"(?: give or take "(?P<within>[^"]+)")?'))
def result_key_is_about(ctx, key, wanted, within):
    """A number that comes of arithmetic, to pytest.approx's tolerance or to the one given."""
    assert ctx.refused is None, f"it was refused: {ctx.refused.message!r}"
    got = dig(ctx.result, key)
    tolerance = {} if within is None else {"abs": float(within)}
    assert got == pytest.approx(float(wanted), **tolerance), f"the result's {key} is {got!r}, not about {wanted}"


@then(parsers.parse('the refusal\'s "{key}" is "{wanted}"'))
def refusal_key_is(ctx, key, wanted):
    """What the refusal raised: its class (`__class__.__name__`) or one of its fields."""
    ctx.refusal_read = True
    assert ctx.refused is not None, f"it was not refused: the result is {ctx.result!r}"
    got = dig(ctx.refused.error, key)
    assert same(got, wanted), f"the refusal's {key} is {got!r}, not {wanted}"
