import os
import logging
import json
import yaml
from pathlib import Path
from typing import Optional
from langchain_nvidia_ai_endpoints import ChatNVIDIA

logger = logging.getLogger(__name__)

def init_evaluator_agent():
    """
    Initializes the ChatNVIDIA agent based on runtime configuration.

    Returns:
        ChatNVIDIA: An instance configured for either NIM or direct API usage.
    """
    config_path = Path(__file__).parent.parent / 'config.yaml'
    if not config_path.exists():
        logger.error(f"Config file not found at: {config_path}")
        raise FileNotFoundError(f"Config file not found at: {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    evaluator_config = config.get("evaluator")
    if evaluator_config is None:
        raise KeyError("Missing 'evaluator' section in config.yaml")

    evaluator = ChatNVIDIA(
        model=evaluator_config["llm_model"],
        messages=evaluator_config["message"],
        api_key=os.getenv("OPENAI_API_KEY_EVAL"),
        base_url=os.getenv("OPENAI_BASE_URL_EVAL"),
        temperature=evaluator_config["llm_temp"],
        top_p=evaluator_config["llm_top_p"],
        max_tokens=evaluator_config["llm_max_tokens"],
    )
    logger.info(f"Successfully Initialize LLM with model: {evaluator_config['llm_model']}")
    return evaluator

def extract_ai_message(result):
    if hasattr(result, "content"):
        return result.content
    if isinstance(result, dict):
        if "AIMessage" in result and isinstance(result["AIMessage"], dict):
            return result["AIMessage"].get("content")
        if "content" in result:
            return result.get("content")
    return None

def build_evaluation_prompt(message, response, spec=None):
    return f"""
You are a Network Intent Evaluation Specialist. Your objective is to audit the chatbot's intent extraction against the conversation context and technical specifications.

## Input Data
**Conversation History (Chronological)**: 
{message}

**Available Intent Specifications**: 
{spec}

**Chatbot Output (JSON to Evaluate)**: 
{response}


## Evaluation Task
Analyze the **Chatbot Output** against the **Conversation History** and **Available Intent Specifications**:

1. **Intent Specification Verification**: 
   - Verify the selected `IntentSpecification` matches the user's **primary goal** based on the specification's `description`.

2. **Schema Compliance**: 
   - The output must contain **all** characteristics defined in the selected specification.
   - Verify values match the format described in each characteristic's `description` and `valueType`.

3. **Value Extraction Validation**: 
   - Validate that extracted values are grounded in the conversation history.
   - Accept **synonym-based inference** for categorical fields (e.g., mapping user verbs to specific terms defined in the spec).
   - Accept **format normalization** to match specification requirements (e.g., normalizing entity names or units).

4. **Completeness Check**: 
   - All characteristic fields must be present. Empty string `""` is acceptable only when information is genuinely absent from the conversation.

## Critical Evaluation Rules

### Rule 1: Conversation as Continuous Context
- Treat all messages as a **cumulative, continuous flow**.
- The **Chatbot Output** represents the **accumulated intent** from the ENTIRE conversation, not just the last message.
- **Scope Persistence**: Information provided in earlier messages (especially identifiers like Cell IDs, Slice IDs, or Region names) persists and applies to subsequent requests. Do not treat these as missing if they appear anywhere in the history.
- **Check All Messages**: You MUST verify the existence of a value against EVERY message in the history. Do not skip the first message.

### Rule 2: Contextual Reference Recognition
When a user mentions an entity in **any phrasing**, recognize it as a valid reference:
- **Contextual declarations**: Statements that establish scope (e.g., "Focus on X", "Working with Y", "Consider slice 1").
- **Standalone Identifiers**: If a message consists primarily of identifiers (e.g., "Cell-1, Slice-1"), treat this as setting the active scope for future intents.
- **Implicit references**: "this", "that", "the slice" → resolve using prior context.

### Rule 3: Composite Value Construction
When a specification requires a **composite value** (e.g., combining multiple pieces of information into a single field):
- Components can come from **different messages** in the conversation.
- Aggregating context from multiple turns is **VALID** and expected.

### Rule 4: Hallucination Definition (Strict)
A value is a hallucination **ONLY IF**:
- It contains information that **cannot be traced** to ANY message in the conversation history.
- It contradicts explicit user statements.

A value is **NOT** a hallucination if:
- It combines information from multiple messages.
- It is derived from a previous message that set the context (e.g., user said "Cell-1" previously, so TargetScope="Cell_1" is valid).
- It normalizes user language to match the specification format (e.g. user says "slice 1", output is "Slice_1").
- It infers standard values from synonyms or contextual declarations.

### Rule 5: Format Normalization Allowance
Accept transformations that align user input with specification format requirements:
- Case normalization.
- Separator standardization (e.g. "Cell 1" -> "Cell_1").
- Unit formatting.

## Output Format
Return ONLY a valid JSON object.

```json
{{
  "score": <integer 0-10>,
  "issues": ["<specific issue description>", ...],
  "feedback": "<concise guidance to improve the chatbot output>"
}}
```

**Scoring Guidelines**:
- **10**: Fully consistent, schema-compliant, all values grounded in context.
- **7-9**: Minor issues (e.g., slight formatting inconsistencies, but values are contextually valid).
- **4-6**: Moderate issues (e.g., missing fields, questionable inferences).
- **0-3**: Major issues (e.g., true hallucinations, wrong intent selection, schema violations).

**Before scoring, verify each flagged issue against Rule 2-4. If a value can be traced to the conversation through contextual declaration, reference, or aggregation, it is NOT an issue.**

Now evaluate the Chatbot Output and generate the JSON.
    """.strip()

def evaluator_agent_invoke(conversation_history_text, intent, spec=None, context=None):
    evaluator_instance = init_evaluator_agent()
    logger.info("Evaluator agent initialized")
    prompt_eval = build_evaluation_prompt(conversation_history_text, json.dumps(intent), spec)
    logger.info("Prompt to evaluator agent:\n%s", prompt_eval)
    eval_result = evaluator_instance.invoke([{"role": "user", "content": prompt_eval}])
    logger.info("Raw agent response: %s", eval_result)
    _last_evaluation = extract_ai_message(eval_result)
    logger.info("Evaluator response: %s", _last_evaluation)
    return _last_evaluation