"""V12 audit adapter backed by immutable ranked warm-start evidence."""
from validation.validators.finite_campaign_validator import FiniteCampaignValidator


class V12Validator(FiniteCampaignValidator):
    validation_id = 'V12'
    schema_version = 1
