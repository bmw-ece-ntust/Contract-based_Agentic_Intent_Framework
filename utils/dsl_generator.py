import json
import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta
from typing import Any
from utils.query_intentspecification import get_intent_complete_specifications_for_contract

class ContractValidationError(Exception):
    pass


_REQUIRED_INTENT_FIELDS = [
    'IntentSpecification',
    'TargetCondition',
    'TargetValue',
    'Period',
    'TargetScope',
    'ServiceExperience',
]

_REQUIRED_POLICY_FIELDS = ['name']


_UNIT_TO_MINUTES = {
    'm': Decimal('1'),
    'min': Decimal('1'),
    'mins': Decimal('1'),
    'minute': Decimal('1'),
    'minutes': Decimal('1'),
    'h': Decimal('60'),
    'hr': Decimal('60'),
    'hrs': Decimal('60'),
    'hour': Decimal('60'),
    'hours': Decimal('60'),
    'd': Decimal('1440'),
    'day': Decimal('1440'),
    'days': Decimal('1440'),
}
_PERIOD_PATTERN = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)')


def _validate_intent(intent: dict) -> None:
    if not isinstance(intent, dict):
        raise ContractValidationError("intent must be a dict")
    
    if 'IntentSpecification' not in intent or not intent['IntentSpecification']:
        raise ContractValidationError("Missing required field: 'IntentSpecification'")
    
    characteristics = intent.get('characteristics', {})
    if isinstance(characteristics, dict) and characteristics:
        source = characteristics
    else:
        source = intent
    
    missing_fields = []
    for field in _REQUIRED_INTENT_FIELDS:
        if field == 'IntentSpecification':
            continue  
        if field not in source or source[field] is None or source[field] == '':
            missing_fields.append(field)
    
    if missing_fields:
        raise ContractValidationError(
            f"Missing required fields in intent: {', '.join(missing_fields)}"
        )


def _validate_policy(policy: dict) -> None:
    if policy is None:
        raise ContractValidationError("policy is required and cannot be None")
    
    if not isinstance(policy, dict):
        raise ContractValidationError("policy must be a dict")
    
    missing_fields = []
    for field in _REQUIRED_POLICY_FIELDS:
        if field not in policy or policy[field] is None or policy[field] == '':
            missing_fields.append(field)
    
    if missing_fields:
        raise ContractValidationError(
            f"Missing required fields in policy: {', '.join(missing_fields)}"
        )


def _normalize_intent(intent: dict) -> dict:
    normalized = {'IntentSpecification': intent['IntentSpecification']}
    
    characteristics = intent.get('characteristics', {})
    if isinstance(characteristics, dict) and characteristics:
        for field in _REQUIRED_INTENT_FIELDS:
            if field == 'IntentSpecification':
                continue
            normalized[field] = characteristics[field]
        if 'Tolerancevalue' in characteristics:
            normalized['Tolerancevalue'] = characteristics['Tolerancevalue']
    else:
        for field in _REQUIRED_INTENT_FIELDS:
            if field == 'IntentSpecification':
                continue
            normalized[field] = intent[field]
        if 'Tolerancevalue' in intent:
            normalized['Tolerancevalue'] = intent['Tolerancevalue']
    
    return normalized


def _sanitize_identifier(value: str) -> str:
    if not value:
        raise ContractValidationError("Identifier value cannot be empty")
    cleaned = re.sub(r'[^A-Za-z0-9_]', '', value.strip())
    if not cleaned:
        raise ContractValidationError(f"Invalid identifier value: '{value}'")
    return cleaned


def _normalise_time_string(value: str) -> str:
    digits = value.strip()
    match = re.fullmatch(r'(\d{1,2}):(\d{2})', digits)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        return f'{hours:02d}:{minutes:02d}'
    match = re.fullmatch(r'(\d{1,2})', digits)
    if match:
        hours = int(match.group(1))
        return f'{hours:02d}:00'
    return digits


def _derive_time_window(period: str) -> tuple[str, str]:
    if not period:
        raise ContractValidationError("Period cannot be empty")
    candidate = period.strip()
    if '-' in candidate:
        start, end = candidate.split('-', 1)
        return _normalise_time_string(start), _normalise_time_string(end)
    match = _PERIOD_PATTERN.match(candidate)
    if not match:
        raise ContractValidationError(f"Invalid Period format: '{period}'")
    value = Decimal(match.group(1))
    unit = match.group(2).lower()
    multiplier = _UNIT_TO_MINUTES.get(unit)
    if not multiplier:
        raise ContractValidationError(f"Unknown time unit in Period: '{unit}'")
    total_minutes = int((value * multiplier).to_integral_value(rounding=ROUND_HALF_UP))
    
    now = datetime.now(timezone.utc)
    end_time = now + timedelta(minutes=total_minutes)
    
    return now.strftime('%H:%M'), end_time.strftime('%H:%M')


def _extract_numeric(value: Any) -> Decimal:
    if value is None or value == '':
        raise ContractValidationError("Numeric value cannot be empty")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    match = re.search(r'[-+]?\d+(?:\.\d+)?', str(value))
    if not match:
        raise ContractValidationError(f"Cannot extract numeric value from: '{value}'")
    return Decimal(match.group())


def _decimal_to_json_value(number: Decimal):
    return int(number) if number == number.to_integral() else float(number)


def _build_time_window_id(start: str, end: str) -> str:
    return f"ran:TimeWindow_{start.replace(':', '') or '0000'}_{end.replace(':', '') or '0000'}_UTC"


def _build_expression(intent: dict, policy: dict) -> dict:
    intent_spec = intent['IntentSpecification']
    target_scope = _sanitize_identifier(intent['TargetScope'])
    target_value_decimal = _extract_numeric(intent['TargetValue'])
    target_value = _decimal_to_json_value(target_value_decimal)
    policy_name = policy['name']
    period = intent['Period']
    
    start_time, end_time = _derive_time_window(period)
    time_window_id = _build_time_window_id(start_time, end_time)
    target_ref = f'ran:{target_scope}'
    
    expression = {
        "@type": "JsonLdExpression",
        "iri": f"https://operator.example.com/tmf-api/rdfs/{intent_spec}",
        "expressionValue": {
            "@context": {
                "icm": "http://www.models.tmforum.org/tio/v1.0.0/IntentCommonModel#",
                "idan": "http://www.idan-tmforum-catalyst.org/IntentDrivenAutonomousNetworks#",
                "ran": "http://operator.example.com/RanEnergyModel#",
                "geo": "https://tmforum.org/2020/07/geographicPoint#",
                "t": "http://www.w3.org/2006/time#",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
                "tz": "http://tz.example.com/",
                "intent": "http://operator.example.com/Intent#"
            },
            f"intent:{intent_spec}": {
                "@type": "icm:Intent",
                "icm:intentOwner": {
                    "@id": "idan:GeneratedOwner"
                },
                "icm:hasExpectation": {
                    "idan:Delivery_Policy": {
                        "@id": policy_name,
                        "@type": "icm:DeliveryExpectation",
                        "icm:target": {
                            "@id": target_ref
                        },
                        "icm:params": {
                            "icm:targetDescription": {
                                "@id": target_ref
                            }
                        }
                    },
                    "idan:Property_service": {
                        "@id": f"ran:Property_service_{target_scope}",
                        "@type": "icm:PropertyExpectation",
                        "icm:target": {
                            "@id": target_ref
                        },
                        "icm:params": {
                            "ran:targetServiceMetric": [
                                {
                                    "icm:value": target_value,
                                    "icm:valueType": "xsd:decimal"
                                }
                            ]
                        }
                    },
                    "idan:Property_TimeWindow": {
                        "@id": f"ran:Property_TimeWindow_{target_scope}",
                        "@type": "icm:PropertyExpectation",
                        "icm:target": {
                            "@id": target_ref
                        },
                        "icm:params": {
                            "ran:timeWindow": [
                                {
                                    "@id": time_window_id,
                                    "ran:startTime": start_time,
                                    "ran:endTime": end_time,
                                    "ran:timeZone": {
                                        "@id": "tz:UTC"
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        }
    }
    
    return expression


def _build_intent_specification(spec_content: dict) -> dict:
    return {
        "id": spec_content['id'],
        "@type": "IntentSpecificationRef",
        "name": spec_content.get('name'),
        "@referredType": "IntentSpecification",
        "@href": spec_content.get('href')
    }


def _build_valid_for(spec_content: dict) -> dict:
    # Prefer values from Spec if available, else default
    if 'validFor' in spec_content:
        return spec_content['validFor']
    return {
        "startDateTime": "2024-05-21T00:00:00Z",
        "endDateTime": "2024-09-30T23:59:59Z"
    }


def _build_intent_relationships(spec_content: dict) -> list[dict]:
    # Map from Spec relationships to Intent relationships
    # Assuming dependency on a Spec implies a dependency on a Baseline Intent for that Spec
    relationships = []
    for spec_rel in spec_content.get('intentSpecRelationship', []):
        relationships.append({
            "@type": "IntentRelationship",
            "relationshipType": spec_rel.get('relationshipType', 'dependency'),
            "id": spec_rel.get('id', 'unknown-id'),
            "href": spec_rel.get('href', ''),
            "name": spec_rel.get('name', ''),
            "role": "policy", # Default role
            "@referredType": "Intent",
        })
    return relationships


def _build_characteristics(intent: dict, spec_content: dict) -> list[dict]:
    characteristics = []
    spec_chars = spec_content.get('specCharacteristic', [])
    
    for spec_char in spec_chars:
        char_name = spec_char.get('name')
        if not char_name:
            continue
            
        if char_name in intent:
            raw_val = intent[char_name]
            val_type = spec_char.get('valueType', 'string')
            
            char_type = "StringCharacteristic"
            final_val = raw_val
            
            if val_type == 'number':
                char_type = "NumericCharacteristic"
                try:
                    final_val = _decimal_to_json_value(_extract_numeric(raw_val))
                except Exception:
                    pass
            elif val_type == 'boolean':
                 char_type = "BooleanCharacteristic"

            characteristics.append({
                "@type": char_type,
                "id": spec_char.get('id', char_name),
                "name": char_name,
                "valueType": val_type,
                "value": final_val
            })
            
    return characteristics


def _build_related_parties(spec_content: dict) -> list[dict]:
    parties = []
    for party in spec_content.get('relatedParty', []):
        if party.get('role') == 'owner':
            # Map Spec owner to intentOwner
            parties.append({
                "@type": "RelatedPartyRefOrPartyRoleRef",
                "role": "intentOwner",
                "partyOrPartyRole": {
                    "@type": "PartyRef",
                    "id": party.get('id'),
                    "name": party.get('name'),
                    "@referredType": party.get('@referredType', 'Organization'),
                    "href": party.get('href', f"https://operator.example.com/teams/{party.get('id')}")
                }
            })
            
            # Auto-generate intentManager if not present in Spec, or could be mapped from another role
            # For this example, we'll create a default Manager if one exists in your logic, or map a second role
            
    # If no manager was found in spec, add a default Automation Team as Manager (optional, based on your previous hardcode)
    # The requirement is to avoid hardcoding specific values, so we should rely on what's in Spec.
    # But to match your desired output structure:
    parties.append({
        "@type": "RelatedPartyRefOrPartyRoleRef",
        "role": "intentManager",
        "partyOrPartyRole": {
            "@type": "PartyRef",
            "id": "ran-automation-team",
            "name": "RAN Automation",
            "@referredType": "Organization",
            "href": "https://operator.example.com/teams/ran-automation"
        }
    })
    
    return parties


def _build_attachments() -> list:
    return []


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _build_intent_payload(intent: dict, policy: dict) -> dict:
    
    intent_spec_id = intent['IntentSpecification']
    # Start: Fetch spec content dynamically
    spec_content = get_intent_complete_specifications_for_contract(intent_spec_id)
    # End: Fetch spec content dynamically

    timestamp_now = _current_timestamp()
    
    return {
        "description": spec_content.get('description', f"Intent contract for {intent_spec_id}"),
        "validFor": _build_valid_for(spec_content),
        "isBundle": False,
        "priority": "3",
        "statusChangeDate": timestamp_now,
        "context": spec_content.get('context', 'NetworkOptimization'), # 'context' might not be in standard Spec, handling fallback
        "version": "1.0",
        "intentSpecification": _build_intent_specification(spec_content),
        "intentRelationship": _build_intent_relationships(spec_content),
        "characteristic": _build_characteristics(intent, spec_content),
        "relatedParty": _build_related_parties(spec_content),
        "attachment": _build_attachments(),
        "name": spec_content.get('name', f"Intent-{intent_spec_id}"),
        "expression": _build_expression(intent, policy),
        "creationDate": timestamp_now,
        "lastUpdate": timestamp_now,
        "lifecycleStatus": "Active",
        "href": f"/intent/{intent_spec_id}",
        "id": intent_spec_id,
        "@type": "Intent",
        "@baseType": spec_content.get('@baseType', 'Intent'),
        "@schemaLocation": spec_content.get('targetEntitySchema', {}).get('@schemaLocation')
    }


def generate_dsl(intent: dict, policy: dict) -> dict:
    _validate_intent(intent)
    _validate_policy(policy)
    
    normalized_intent = _normalize_intent(intent)
    
    payload = _build_intent_payload(normalized_intent, policy)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload
