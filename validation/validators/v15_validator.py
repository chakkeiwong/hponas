"""Compatibility entry for immutable V15a finite reference evidence."""
from validation.validators.finite_campaign_validator import FiniteCampaignValidator


class V15Validator(FiniteCampaignValidator):
    validation_id = 'V15a'
    schema_version = 1
