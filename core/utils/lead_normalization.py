from typing import Dict, Tuple

from core.utils.validators import validate_email_strict, normalize_phone_e164, extract_name, _normalize_key


# Canonical map for common business/custom fields (DE/EN -> EN canonical)
CANONICAL_CUSTOM_KEYS = {
    # Company
    'firma': 'company',
    'unternehmen': 'company',
    'unternehmensname': 'company',
    'company': 'company',
    'company_name': 'company',
    'firmenname': 'company',
    # Industry / Branche
    'branche': 'industry',
    'industrie': 'industry',
    'industry': 'industry',
    'sektor': 'industry',
    # Employee count
    'mitarbeiteranzahl': 'employee_count',
    'anzahl_mitarbeiter': 'employee_count',
    'mitarbeiter': 'employee_count',
    'employees': 'employee_count',
    'employee_count': 'employee_count',
    # Budget
    'budget': 'budget',
}


CORE_KEYS = {'first_name', 'last_name', 'full_name', 'email', 'phone'}


def _pick_email(raw_email: str) -> str:
    """Pick a single valid email; fallback to raw string containing '@'."""
    if not raw_email:
        return ''
    valid = validate_email_strict(raw_email)
    return valid or (raw_email if '@' in raw_email else '')


def _pick_phone(raw_phone: str) -> str:
    """Normalize phone to E.164; fallback minimal sanitized digits if needed."""
    if not raw_phone:
        return ''
    p = normalize_phone_e164(raw_phone, default_region='DE')
    if p:
        return p
    # fallback: remove non-digits except leading +
    digits = ''.join(ch for ch in raw_phone if ch.isdigit() or ch == '+')
    return digits


def canonicalize_lead_payload(row: Dict) -> Dict:
    """
    Provider-agnostic normalization for lead payloads.
    - Guarantees singular first_name, last_name, email, phone
    - Converts full_name to first/last and does not expose full_name
    - Flattens remaining keys into variables with EN-canonical names
    """
    # 1) Normalize incoming row keys for known fields
    # Accept both `name/surname` and `first_name/last_name`
    raw_first = row.get('first_name') or row.get('name') or ''
    raw_last = row.get('last_name') or row.get('surname') or ''
    raw_full = row.get('full_name') or row.get('fullName') or ''
    raw_email = row.get('email') or row.get('mail') or ''
    raw_phone = row.get('phone') or row.get('telefon') or ''

    # 2) Determine first/last via extract_name when needed
    first, last, _ = extract_name(str(raw_first or ''), str(raw_last or ''), str(raw_full or '')) or (None, None, None)
    if not first:
        first = str(raw_first or raw_full or '').strip()
    if not last:
        last = str(raw_last or '').strip()

    # 3) Email and phone (singular)
    email = _pick_email(str(raw_email or ''))
    phone = _pick_phone(str(raw_phone or ''))

    # 4) Variables: start with provided variables/custom structures if any
    variables: Dict = {}
    raw_variables = row.get('variables') or {}
    if isinstance(raw_variables, dict):
        # Flatten nested 'custom' if present
        custom = raw_variables.get('custom') if isinstance(raw_variables.get('custom'), dict) else {}
        for k, v in {**{_normalize_key(str(k)): v for k, v in raw_variables.items() if k not in {'custom', 'matched_keys'}}, **custom}.items():
            k_norm = _normalize_key(str(k))
            if k_norm in CORE_KEYS:
                continue
            variables[CANONICAL_CUSTOM_KEYS.get(k_norm, k_norm)] = v

    # Also include any top-level non-core fields present directly on row
    for k, v in row.items():
        if k in {'variables', 'matched_keys'}:
            continue
        k_norm = _normalize_key(str(k))
        if k_norm in CORE_KEYS:
            continue
        # Avoid overwriting canonicalized variable chosen above
        canonical = CANONICAL_CUSTOM_KEYS.get(k_norm, k_norm)
        if canonical not in variables and isinstance(v, (str, int, float)):
            variables[canonical] = v

    # 5) Build output (no full_name)
    return {
        'first_name': (first or '').strip(),
        'last_name': (last or '').strip(),
        'email': (email or '').strip(),
        'phone': (phone or '').strip(),
        'variables': variables,
    }






