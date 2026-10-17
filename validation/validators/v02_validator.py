"""V02 compatibility audit for the complete recorded event/runtime corpus."""

from validation.validators.finite_campaign_validator import FiniteCampaignValidator


class V02Validator(FiniteCampaignValidator):
    validation_id = "V02"
