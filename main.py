import logging
from pathlib import Path
from utils.human_language_api import run_server
from utils.chatbot import initialize_chatbot, handle_message

# Configure logging
log_dir = Path(__file__).resolve().parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "application.log"

# Configure root logger to ensure all module loggers inherit these settings
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True  # Force reconfiguration to override any existing configuration
)

# Set logging level for all relevant modules
for logger_name in ['utils.chatbot', 'utils.Agent', 'utils.evaluator', 
                     'utils.dsl_generator', 'utils.intent_contract', 
                     'utils.query_context', 'utils.query_intentspecification',
                     'utils.human_language_api']:
    logging.getLogger(logger_name).setLevel(logging.INFO)

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    logger.info("Starting application...")
    initialize_chatbot()
    run_server(
        host='0.0.0.0',
        port=5200,
        debug=False,
        message_handler=handle_message
    )


