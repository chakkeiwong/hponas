"""Promotion counts follow ceil for the represented eta, including large n."""

from fractions import Fraction
import math

import numpy as np
import pytest

from hponas.schedulers import _ceil_population_ratio


@pytest.mark.parametrize("population", [0, 1, 2, 3, 6, 7, 2**53 - 1, 2**53, 2**53 + 1, 2**63 - 1])
@pytest.mark.parametrize("eta", [2, 3, 2**53, np.int64(3), 1.5, np.float32(2.5),
                                math.nextafter(2., 0.), math.nextafter(2., 3.)])
def test_exact_ceiling_against_rational_oracle(population, eta):
    divisor = Fraction(int(eta)) if isinstance(eta, (int, np.integer)) else Fraction(float(eta))
    expected = math.ceil(Fraction(population) / divisor)
    assert _ceil_population_ratio(population, eta) == expected
