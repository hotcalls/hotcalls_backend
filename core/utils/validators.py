import re
import unicodedata
from typing import Optional, Tuple

from django.core.validators import validate_email
from django.core.exceptions import ValidationError

try:
    import phonenumbers
except Exception:  # pragma: no cover
    phonenumbers = None


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_key(key: str) -> str:
    key = unicodedata.normalize('NFKD', key)
    key = ''.join(c for c in key if not unicodedata.combining(c))
    key = key.lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = re.sub(r"_+", "_", key).strip('_')
    return key


def validate_email_strict(value: str) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    try:
        validate_email(value)
    except ValidationError:
        if not EMAIL_REGEX.match(value):
            return None
    return value


def normalize_phone_e164(value: str, default_region: str = 'DE') -> Optional[str]:
    if not value:
        return None
    raw = str(value).strip()
    # Convert leading 00 to +
    if raw.startswith('00'):
        raw = '+' + raw[2:]
    try:
        if phonenumbers is None:
            return None
        if raw.startswith('+'):
            num = phonenumbers.parse(raw, None)
        else:
            num = phonenumbers.parse(raw, default_region or 'DE')
        if not phonenumbers.is_possible_number(num):
            return None
        if not phonenumbers.is_valid_number(num):
            return None
        e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        # Ensure strict + and digits only
        if not e164.startswith('+'):
            return None
        if not re.fullmatch(r"\+[0-9]+", e164):
            # remove any non-digits just in case
            e164 = '+' + re.sub(r"\D+", "", e164)
        return e164
    except Exception:
        return None


def extract_name(first: Optional[str], last: Optional[str], full: Optional[str]) -> Optional[Tuple[str, str, str]]:
    first = (first or '').strip()
    last = (last or '').strip()
    full = (full or '').strip()

    if first and last:
        return first, last, f"{first} {last}".strip()

    # full name with tokens
    if full:
        tokens = full.split()
        if len(tokens) >= 2:
            return tokens[0], ' '.join(tokens[1:]), full
        # one-word name allowed
        return full, '', full

    # fallback: if only one of first/last exists, accept one-word name
    if first and not last:
        return first, '', first
    if last and not first:
        return last, '', last

    return None


__all__ = [
    'validate_email_strict',
    'normalize_phone_e164',
    'extract_name',
    '_normalize_key',
]


