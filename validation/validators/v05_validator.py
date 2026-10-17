"""V05 audit requires immutable v4 execution artifacts."""

from validation.validators.finite_campaign_validator import FiniteCampaignValidator


class V05Validator(FiniteCampaignValidator):
    validation_id = "V05"
    schema_version = 4
