"""V07 audit adapter backed by immutable finite DEHB evidence."""
from validation.validators.finite_campaign_validator import FiniteCampaignValidator


class V07Validator(FiniteCampaignValidator):
    validation_id = 'V07'
    schema_version = 1
