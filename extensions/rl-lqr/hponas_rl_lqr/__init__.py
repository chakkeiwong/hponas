"""Optional, independently qualified known-answer RLlib companion."""

from .reference import LQRSpec, enumerate_policy, riccati, rational_reference

__all__ = ['LQRSpec', 'enumerate_policy', 'riccati', 'rational_reference']
