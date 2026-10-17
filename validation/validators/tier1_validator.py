"""Exact finite Tier-1 audit adapter; historical diagnostics cannot certify."""
from validation.protocol_identity import canonical_id
from validation.tier1_contract import ENTRIES
from validation.validators.finite_campaign_validator import FiniteCampaignValidator


class Tier1FiniteValidator(FiniteCampaignValidator):
    schema_version=1

    def __init__(self,validation_id,run_dir=None):
        self.validation_id=canonical_id(validation_id)
        if self.validation_id not in ENTRIES:
            raise ValueError('Exact finite Tier-1 entry required')
        super().__init__(run_dir)
