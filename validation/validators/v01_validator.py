"""V01 compatibility audit for the authorized complete finite corpus."""

from validation.validators.finite_campaign_validator import FiniteCampaignValidator


class V01Validator(FiniteCampaignValidator):
    validation_id = "V01"
