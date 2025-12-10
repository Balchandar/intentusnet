from .models import IntentEnvelope
from .errors import ValidationError


def validate_envelope(env: IntentEnvelope) -> None:
    if not env.intent or not isinstance(env.intent, str):
        raise ValidationError("Intent must be a non-empty string")
    if not isinstance(env.payload, dict):
        raise ValidationError("Payload must be a dict")
