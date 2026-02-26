import requests
import logging
import re
from typing import Any, List
from neo4j import GraphDatabase
from utils.query_intentspecification import get_intent_endpoint, get_rapp_name

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_policy_data(data: dict, timeout: int = 120) -> dict:
    intent_id = data.get("IntentSpecification")
    if not intent_id:
        raise ValueError("Input data must contain 'IntentSpecification'")

    rapp_name = get_rapp_name(intent_id)
    url = get_intent_endpoint(rapp_name)
    if not url:
        raise ValueError(f"Could not find endpoint for intent: {intent_id}")

    try:
        logger.info(f"Requesting policy data from {url} with payload: {data}")
        response = requests.post(url, json=data, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to get policy data: {exc}") from exc