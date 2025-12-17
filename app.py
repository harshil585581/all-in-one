# Main Flask Application - Entry Point
# Unified backend service with modular structure
import os
from flask import Flask, jsonify
from flask_cors import CORS

# Import blueprints
from routes.image import image_bp
from routes.video import video_bp
from routes.audio import audio_bp
from routes.pdf import pdf_bp
from routes.conversion import conversion_bp

# Create Flask app
app = Flask(__name__)

# Configure CORS
# Use environment variable for production frontend URL
# Falls back to allowing all origins for development
frontend_origin = os.environ.get('FRONTEND_URL', '*')
CORS(app, resources={r"/*": {
    "origins": frontend_origin,  # Set FRONTEND_URL env var in production
    "allow_headers": "*",
    "expose_headers": "*",
    "methods": ["GET", "POST", "OPTIONS"],
}}, supports_credentials=False)

# Set max upload size (500 MB)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

# Register blueprints - All endpoints keep their original paths
# No URL prefix to maintain backward compatibility
app.register_blueprint(image_bp)
app.register_blueprint(video_bp)
app.register_blueprint(audio_bp)
app.register_blueprint(pdf_bp)
app.register_blueprint(conversion_bp)


@app.route('/', methods=['GET'])
def index():
    """API root endpoint"""
    return jsonify({
        "status": "ok",
        "message": "Upscale Fullstack Backend API",
        "version": "2.0",
        "endpoints": {
            "image": [
                "/img-compress",
                "/img-jpg",
                "/img-png",
                "/img-webp",
                "/upscale",
                "/remove-imgbg",
                "/watermark-imgvideo"
            ],
            "video": [
                "/video-upscale",
                "/download-video-batch"
            ],
            "audio": [
                "/download-audio-batch"
            ],
            "pdf": [
                "/protect-pdf",
                "/unlock-pdf",
                "/pdf-to-word",
                "/watermark-files"
            ],
            "conversion": [
                "/file-pdf",
                "/convert-all-to-ppt",
                "/compress",
                "/status"
            ]
        }
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "upscale-backend"}), 200


# Error handlers
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "File too large. Maximum size is 500MB"}), 413


@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({"error": "Internal server error", "message": str(error)}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404


if __name__ == '__main__':
    import os
    
    # Get port from environment variable (for Railway, Render, Heroku, etc.)
    # Falls back to 5000 for local development
    port = int(os.environ.get('PORT', 5000))
    
    # Get environment mode
    env = os.environ.get('FLASK_ENV', 'development')
    is_production = env == 'production'
    
    print("=" * 60)
    print("Upscale Fullstack Backend Service")
    print("=" * 60)
    print(f"Environment: {env}")
    print(f"Port: {port}")
    print(f"Host: 0.0.0.0 (accessible from network)")
    print("All endpoints available - See / for list")
    print("=" * 60)
    
    # Run the app
    # Use 0.0.0.0 to allow external connections (required for Railway/Render)
    # Debug mode OFF in production, ON in development
    app.run(
        host='0.0.0.0',  # Changed from 127.0.0.1 to allow external access
        port=port,       # Use environment PORT variable
        debug=not is_production  # False in production, True in development
    )
