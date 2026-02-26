import logging
import json
from textwrap import dedent
from typing import Any, Dict, List, Optional, Sequence

from utils.Agent import init_agent
from utils.query_context import get_policy_data
from utils.query_intentspecification import get_intent_specifications
from utils.evaluator import evaluator_agent_invoke
from utils.dsl_generator import generate_dsl
from utils.intent_contract import register_intent_contract

logger = logging.getLogger(__name__)
_agent_instance = None
MAX_HISTORY = 10
MAX_EVALUATION_ATTEMPTS = 5
_conversation_history: List[str] = []
_last_intent: Optional[Dict[str, Any]] = None
_last_evaluation: Optional[Dict[str, Any]] = None

def initialize_chatbot() -> None:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = init_agent()
        logger.info("Chatbot agent initialized")

def _get_agent():
    if _agent_instance is None:
        initialize_chatbot()
    return _agent_instance

def _format_history(messages: Sequence[str]) -> str:
    cleaned = [str(msg) for msg in messages if str(msg).strip()]
    return "\n".join(f"- {msg}" for msg in cleaned) if cleaned else "None"

def _clear_conversation_state() -> None:
    """Clear all accumulated conversation state for a fresh start."""
    global _conversation_history, _last_intent, _last_evaluation
    _conversation_history.clear()
    _last_intent = None
    _last_evaluation = None
    logger.info("Conversation state cleared for next session")

def _intent_profiling_prompt(user_message: str, intent: str = "", previous_user_messages: Optional[Sequence[str]] = None, spec: Optional[Sequence[str]] = None) -> str:
    messages = []
    if previous_user_messages:
        messages = [str(msg) for msg in previous_user_messages if str(msg).strip()]
    previous_messages_text = _format_history(messages)
    intent_text = json.dumps(_last_intent, ensure_ascii=False) if _last_intent else "None"
    return dedent(
        f"""
        You are a Network Intent Profiling Expert. Your objective is to extract user intent from natural language and map it to a strict technical specification.

        ## Context
        **Available Intent Specifications**: {spec}
        
        **Conversation History**: {previous_messages_text}
        
        **Current Accumulated Intent**: {intent_text}

        **New User Message**: {user_message}

        ## Task
        Analyze the **New User Message** in the context of the **Conversation History** to construct or update the intent JSON. Follow these steps:

        1. **Intent Specification Selection**: 
           - Review **Available Intent Specifications** and select the ID that best matches the user's goal description.
           - If **Current Accumulated Intent** is active, prioritize it unless the user explicitly changes the **primary objective**.
        2. **Schema Compliance**: The `characteristics` object in your output must contain **every** characteristic defined in the selected specification. Use the exact `name` property from the specification as the key.
        3. **Value Extraction & Inference**: 
           - Extract precise values based on the `description` provided for each characteristic in the specification.
           - For categorical fields, **infer** the standard value from synonyms found in the user's message (e.g., map user's intent verbs to the specific terms required by the spec).
           - If a value cannot be inferred from the conversation or context, set it to `""`.
        4. **Mandatory Output Generation**: You MUST generate the full JSON structure. Even if you cannot extract a value for a characteristic, you must include the key with an empty string `""` as the value. Do not fail to generate JSON because of missing values.

        ## Rules
        Adhere strictly to the following constraints:

        1. **Contextual Continuity**: Treat the conversation as a continuous flow. If the **Current Accumulated Intent** is active, assume the **New User Message** is a refinement, constraint, or additional detail for that intent unless explicitly stated otherwise.
        2. **Cumulative State Management**: 
           - Merge new information into the **Current Accumulated Intent**.
           - **Preserve** existing values unless the **New User Message** explicitly corrects them.
           - **Populate** empty fields (`""`) when new details are extracted.

        ## Output Format
        Return ONLY a valid JSON object. Do not include explanations or comments.

        ```json
        {{
          "IntentSpecification": "<ID of the selected Intent Specification>",
          "characteristics": {{
            "<CharacteristicName1>": "<Extracted Value or Empty String>",
            "<CharacteristicName2>": "<Extracted Value or Empty String>"
          }}
        }}
        ```
        IMPORTANT: Ensure ALL characteristics from the spec are listed. Do NOT include any comments in the JSON output.
        Now process the inputs and generate the JSON.
        """
    ).strip()

def _intent_profiling_evaluation_prompt(intent: str = "", previous_user_messages: Optional[Sequence[str]] = None, spec: Optional[Sequence[str]] = None, _last_evaluation: Optional[Dict[str, Any]] = None) -> str:
    history_text = _format_history(previous_user_messages or [])
    if isinstance(_last_evaluation, dict):
        evaluation_text = json.dumps(_last_evaluation, ensure_ascii=False, indent=2)
    elif _last_evaluation:
        evaluation_text = str(_last_evaluation)
    else:
        evaluation_text = "None"

    intent_text = json.dumps(_last_intent, ensure_ascii=False) if _last_intent else "None"

    return dedent(
        f"""
        You are a Network Intent Profiling Expert. Your task is to refine the extracted intent based on evaluator feedback and conversation history.

        ## Context
        **Available Intent Specifications**: {spec}
        
        **Conversation History**: {history_text}
        
        **Current Accumulated Intent**: {intent_text}
        
        **Evaluator Feedback**:
        {evaluation_text}

        ## Your Task
        1. **Resolve Feedback**: Carefully review the **Evaluator Feedback** and address every listed issue.
        2. **Verify Context**: Use the **Conversation History** to confirm, correct, or complete the fields flagged by the evaluator.
        3. **State Refinement**: Preserve correct existing values. Update only what is necessary to resolve the feedback or what the context clarifies.
        4. **Schema Compliance**: Ensure the output strictly follows the format defined in the selected `IntentSpecification`. Refer to the `description` of each characteristic in the **Available Intent Specifications** to ensure values are valid.
        5. **Handling Missing Info**: If the context does not provide the missing information requested, leave the field as an empty string `""`.

        ## Output Format
        Return ONLY a valid JSON object matching the `IntentSpecification` structure.
        """
    ).strip()


def _normalize_response(raw: Any) -> str:
    content = getattr(raw, 'content', raw)
    if isinstance(content, (list, tuple)):
        return " ".join(str(item) for item in content)
    return str(content)

def _ensure_dict_evaluation(evaluation: Any) -> Dict[str, Any]:
    if isinstance(evaluation, dict):
        return evaluation
    if isinstance(evaluation, str):
        try:
            return _retrieve_jsonoutput_response(evaluation)
        except ValueError as exc:
            logger.warning("Failed to parse evaluator response as JSON: %s", exc)
            return {"raw": evaluation}
    return {}

def _collect_missing_feedback(intent: Dict[str, Any], specs: List[Dict[str, Any]]) -> List[str]:
    intent_id = intent.get("IntentSpecification")
    if not intent_id:
        return ["Please provide more details about your goal"]

    target_spec = next((s for s in specs if s.get("id") == intent_id), None)
    if not target_spec:
        return []

    missing_fields = []
    intent_chars = intent.get("characteristics", {})
    
    for char_spec in target_spec.get("characteristics", []):
        char_name = char_spec.get("name")
        val = intent_chars.get(char_name)
        # Check if the field is missing (None) or empty string
        if char_name and (val is None or val == ""):
            missing_fields.append(f"'{char_name}'")
            
    if missing_fields:
        fields_str = ", ".join(missing_fields)
        return [f"Please provide more information for {fields_str}."]
    return []

def handle_message(user_message: str, previous_user_messages: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    try:
        global _last_intent, _last_evaluation
        logger.info("Routing message to agent")
        history = list(previous_user_messages) if previous_user_messages else list(_conversation_history)
        logger.info("Previous user messages: %s", history)
        agent = _get_agent()
        current_intent = ""

        # Get intent specification
        spec = get_intent_specifications()
        logger.info(f"Intent Specifications with Characteristics: {spec}")

        prompt = _intent_profiling_prompt(user_message, current_intent, history, spec)
        logger.info("Prompt to profiling agent:\n%s", prompt)
        raw_response = agent.invoke(prompt)
        logger.info("Raw agent response: %s", raw_response)
        normalized = _normalize_response(raw_response)
        intent = _retrieve_jsonoutput_response(normalized)
        logger.info("Agent response: %s", normalized)

        _conversation_history.append(user_message)
        if len(_conversation_history) > MAX_HISTORY:
            del _conversation_history[:-MAX_HISTORY]
        _last_intent = intent
        missing_feedback = _collect_missing_feedback(intent, spec)
        if missing_feedback:
            return "\n".join(missing_feedback)
        else:
            logger.info("Only_profiling Agent extracted complete intent: %s", intent)
        # ==========================================
        ### If you want to skip evaluator-based refinement, uncomment the following block ###
            # logger.info("Intent profiling complete with all fields populated.")
            # # policy = get_policy_data(_last_intent)
            # # logger.info(f"Policy Data: {policy}")
            # # # Example Output: INFO:utils.chatbot:Policy Data: {'name': 'Property_energyReduction_02'}
            # # dsl = generate_dsl(intent, policy)
            # # logger.info("Generated DSL: %s", dsl)
            # # register_intent_contract(dsl)
            # return _last_intent
        # ==========================================

        # ==========================================
        ### The following block is for evaluator-based refinement loop ###
        attempts = 0
        while True:
            conversation_history_text = get_conversation_history_text()
            raw_evaluation = evaluator_agent_invoke(conversation_history_text, intent, spec)
            _last_evaluation = _ensure_dict_evaluation(raw_evaluation)
            score = _last_evaluation.get("score")
            logger.info("Evaluator score: %s", score)
            if score == 10:
                logger.info("Intent profiling complete with all fields populated.")
                # policy = get_policy_data(_last_intent)
                # if policy['name'] == "feasibility_validation_failed":
                #     return "The specified intent is not feasible based on current network conditions. Please adjust your requirements."
                # else:
                #     logger.info(f"Policy Data: {policy}")
                #     # Example Output: INFO:utils.chatbot:Policy Data: {'name': 'Property_energyReduction_02'}
                #     logger.info(f"Generating DSL for intent: {_last_intent}")
                #     dsl = generate_dsl(intent, policy)
                #     logger.info("Generated DSL: %s", dsl)
                #     register_intent_contract(dsl)
                #     # Clear accumulated state for next conversation
                #     _clear_conversation_state()
                return _last_intent
            attempts += 1
            if attempts >= MAX_EVALUATION_ATTEMPTS:
                raise RuntimeError("Evaluator score did not reach 10 within allowed attempts")
            prompt = _intent_profiling_evaluation_prompt(current_intent, list(_conversation_history), spec, _last_evaluation)
            raw_response = agent.invoke(prompt)
            logger.info("Raw agent response: %s", raw_response)
            normalized = _normalize_response(raw_response)
            logger.info("Agent retry response: %s", normalized)
            intent = _retrieve_jsonoutput_response(normalized)
            _last_intent = intent
            missing_feedback = _collect_missing_feedback(intent, spec)
            if missing_feedback:
                return "\n".join(missing_feedback)
        # ==========================================
    except Exception as err:
        logger.error("Error while invoking agent: %s", err)
        raise

def _retrieve_jsonoutput_response(text: str) -> Dict[str, Any]:
    import re
    # Remove <think>...</think> blocks that may contain invalid JSON with comments
    # This is safe for models without thinking mode - re.sub returns original text if no match
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    start = text.find('{')
    if start == -1:
        raise ValueError("No JSON object found in response")
    segment = text[start:]
    depth = 0
    end = None
    for index, char in enumerate(segment):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise ValueError("Incomplete JSON object in response")
    json_str = segment[:end].strip()
    return json.loads(json_str)

def get_conversation_history_text() -> str:
    return _format_history(_conversation_history)

def get_last_intent() -> Optional[Dict[str, Any]]:
    return _last_intent

def get_last_evaluation() -> Optional[Dict[str, Any]]:
    return _last_evaluation