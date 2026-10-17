"""V04-T0 audit requires immutable v4 execution artifacts."""

from validation.validators.finite_campaign_validator import FiniteCampaignValidator


class V04Validator(FiniteCampaignValidator):
    validation_id = "V04-T0"
    schema_version = 4
