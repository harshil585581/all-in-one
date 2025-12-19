# Main Flask Application - Entry Point
# Unified backend service with modular structure
import os
from flask import Flask, jsonify, request
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
# Allow multiple origins for both development and production
# Supports localhost for dev and production URLs
allowed_origins = os.environ.get('FRONTEND_URL', 'http://localhost:4200,http://localhost:3000,https://all-in-one-frontend.netlify.app')

# Split comma-separated origins or use wildcard
if allowed_origins == '*':
    origins_list = '*'
else:
    origins_list = [origin.strip() for origin in allowed_origins.split(',')]

CORS(app, resources={r"/*": {
    "origins": origins_list,
    "allow_headers": ["Content-Type", "Authorization", "Accept", "X-Requested-With"],
    "expose_headers": ["Content-Disposition"],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "max_age": 3600,
    "supports_credentials": False
}})

# Set max upload size (500 MB)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024


# Add CORS headers to all responses (ensures preflight requests are handled)
@app.after_request
def after_request(response):
    """Ensure CORS headers are present on all responses, including OPTIONS"""
    origin = request.headers.get('Origin')
    
    # Set Access-Control-Allow-Origin header
    if origin:
        if origins_list == '*':
            response.headers['Access-Control-Allow-Origin'] = '*'
        elif isinstance(origins_list, list) and origin in origins_list:
            response.headers['Access-Control-Allow-Origin'] = origin
        else:
            # Fallback: allow localhost origins in development
            if 'localhost' in origin or '127.0.0.1' in origin:
                response.headers['Access-Control-Allow-Origin'] = origin
    
    # Set other CORS headers
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
    response.headers['Access-Control-Max-Age'] = '3600'
    
    return response

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
