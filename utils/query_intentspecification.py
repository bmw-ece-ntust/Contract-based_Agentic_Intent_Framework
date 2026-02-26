import requests

def _extract_intents_id(payload):
    intents = []
    if isinstance(payload, dict):
        if payload.get("@type") == "IntentSpecification" and isinstance(payload.get("id"), str):
            intents.append({
                "id": payload["id"],
                "description": payload.get("description")
            })
        for value in payload.values():
            intents.extend(_extract_intents_id(value))
    elif isinstance(payload, list):
        for item in payload:
            intents.extend(_extract_intents_id(item))
    return intents

def _extract_intents_characteristics(payload):
    intents = []
    if isinstance(payload, dict):
        if payload.get("@type") == "IntentSpecification":
            characteristics = []
            for spec in payload.get("specCharacteristic", []):
                if isinstance(spec, dict):
                    spec_id = spec.get("id")
                    if spec_id and spec_id.startswith("input_"):
                        characteristics.append({
                            "name": spec.get("name"),
                            "description": spec.get("description"),
                            "valueType": spec.get("valueType"),
                        })
            intents.append({
                "id": payload.get("id"),
                "characteristics": characteristics,
            })
        for value in payload.values():
            intents.extend(_extract_intents_characteristics(value))
    elif isinstance(payload, list):
        for item in payload:
            intents.extend(_extract_intents_characteristics(item))
    return intents

def get_intent_specifications(endpoint="http://<intent-management-ip>:<port>/intentSpecification", timeout=10):
    response = requests.get(endpoint, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    intent_entries = _extract_intents_id(payload)
    characteristics_lookup = {
        intent["id"]: intent.get("characteristics", [])
        for intent in _extract_intents_characteristics(payload)
        if intent.get("id")
    }
    unique = {}
    for intent in intent_entries:
        intent_id = intent.get("id")
        if not intent_id or intent_id == "EventLiveBroadcast_Spec" or intent_id in unique:
            continue
        unique[intent_id] = {
            **intent,
            "characteristics": characteristics_lookup.get(intent_id, []),
        }
    return list(unique.values())

def get_intent_complete_specifications_for_contract(intent_id, endpoint="http://<intent-management-ip>:<port>/intentSpecification", timeout=10):
    """
    Fetch the complete Intent Specification JSON for a specific intent_id.
    GET http://<host>:<port>/intentSpecification/<intent_id>
    """
    url = f"{endpoint.rstrip('/')}/{intent_id}"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()

def get_rapp_name(intent_id, endpoint="http://<intent-management-ip>:<port>/intentSpecification", timeout=10):
    response = requests.get(endpoint, timeout=timeout)
    response.raise_for_status()
    payload = response.json()

    def _find_rapp_name(data):
        if isinstance(data, dict):
            if data.get("@type") == "IntentSpecification" and data.get("id") == intent_id:
                for spec in data.get("specCharacteristic", []):
                    if isinstance(spec, dict) and spec.get("id") == "rApp_name":
                        return spec.get("name")
            for value in data.values():
                result = _find_rapp_name(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = _find_rapp_name(item)
                if result:
                    return result
        return None

    return _find_rapp_name(payload)

def get_intent_endpoint(rapp_name, endpoint="http://<service-management-exposure-ip>:<port>/services", timeout=10):
    if not rapp_name:
        return None

    response = requests.get(endpoint, timeout=timeout)
    response.raise_for_status()
    payload = response.json()

    target_service = None
    services = []
    
    if isinstance(payload, dict):
        if "data" in payload and isinstance(payload["data"], list):
            services = payload["data"]
        elif payload.get("name") == rapp_name:
            services = [payload]
    elif isinstance(payload, list):
        services = payload

    for service in services:
        if service.get("name") == rapp_name:
            target_service = service
            break

    if target_service:
        protocol = target_service.get("protocol", "http")
        host = target_service.get("host")
        port = target_service.get("port")
        path = target_service.get("path", "")
        
        if host and port:
            return f"{protocol}://{host}:{port}{path}"

    return None
