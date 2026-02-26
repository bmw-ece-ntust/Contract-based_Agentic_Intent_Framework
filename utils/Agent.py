import os
import yaml
import logging
from pathlib import Path
from langchain_nvidia_ai_endpoints import ChatNVIDIA

logger = logging.getLogger(__name__)

def init_agent():
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

    profiling_config = config.get("profiling")
    if profiling_config is None:
        raise KeyError("Missing 'profiling' section in config.yaml")

    llm = ChatNVIDIA(
        model=profiling_config["llm_model"],
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        messages=profiling_config["message"],
        temperature=profiling_config["llm_temp"],
        top_p=profiling_config["llm_top_p"],
        max_tokens=profiling_config["llm_max_tokens"],
        streaming=True,
        timeout=120
    )

    logger.info(f"Successfully Initialize LLM with model: {profiling_config['llm_model']}")
    return llm