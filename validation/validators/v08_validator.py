"""V08 audit adapter backed by immutable finite raw evidence."""
from validation.validators.finite_campaign_validator import FiniteCampaignValidator


class V08Validator(FiniteCampaignValidator):
    validation_id = 'V08'
    schema_version = 1
