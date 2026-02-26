import logging
from flask import Flask, request, jsonify

logger = logging.getLogger(__name__)

def create_app(message_handler=None):
    """Create and configure the Flask application"""
    app = Flask(__name__)
    
    app.logger.handlers = []
    app.logger.propagate = True

    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint"""
        return jsonify({"status": "healthy"}), 200

    @app.route('/human_language', methods=['POST'])
    def process_human_language():
        """
        Process human language message
        """
        try:
            data = request.get_json()
            if not data or 'message' not in data:
                return jsonify({
                    "status": "error",
                    "message": "Missing 'message' field in request body"
                }), 400

            user_message = data['message']
            logger.info(f"Received message: {user_message}")

            if message_handler:
                result = message_handler(user_message)
            else:
                result = {"status": "success"}
            if result is None:
                result = {"status": "success", "response": "No response from handler"}
                return jsonify(result), 200
            elif isinstance(result, dict):
                # Contract successfully processed - don't expose internal result
                logger.info(f"Sending contract response: {result}")
                return jsonify({"status": "success", "message": "Your intent contract successfully processed"}), 200
            else:
                # Handler returned a string (e.g. follow-up question) - pass it back to the user
                result = {"status": "success", "response": str(result)}
                return jsonify(result), 200
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500

    return app


def run_server(host='0.0.0.0', port=5200, debug=False, message_handler=None):
    """Run the Flask server"""
    app = create_app(message_handler=message_handler)
    logger.info("Starting Human Language API Server...")
    app.run(
        host=host,
        port=port,
        debug=debug,
        use_reloader=False
    )
