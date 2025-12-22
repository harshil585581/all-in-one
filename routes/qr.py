# QR code routes - Endpoints for QR code generation
from flask import Blueprint, request, send_file, jsonify
from qr_generator import generate_qr_code

qr_bp = Blueprint("qr", __name__)


@qr_bp.route("/generate-qr", methods=["POST", "OPTIONS"])
def generate_qr():
    """
    Generate QR code endpoint.
    
    Expected JSON payload:
    {
        "data": "https://example.com",
        "size": 300,
        "error_correction": "M",
        "foreground": "#000000",
        "background": "#ffffff"
    }
    """
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    
    try:
        # Get JSON data from request
        req_data = request.get_json()
        
        if not req_data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Extract parameters
        qr_data = req_data.get('data', '')
        size = int(req_data.get('size', 300))
        error_correction = req_data.get('error_correction', 'M')
        foreground = req_data.get('foreground', '#000000')
        background = req_data.get('background', '#ffffff')
        
        # Validate required data
        if not qr_data:
            return jsonify({'error': 'QR code data is required'}), 400
        
        # Validate size
        if size < 100 or size > 2000:
            return jsonify({'error': 'Size must be between 100 and 2000 pixels'}), 400
        
        # Validate error correction level
        if error_correction.upper() not in ['L', 'M', 'Q', 'H']:
            return jsonify({'error': 'Invalid error correction level'}), 400
        
        # Generate QR code
        qr_image = generate_qr_code(
            data=qr_data,
            size=size,
            error_correction=error_correction,
            foreground=foreground,
            background=background
        )
        
        # Return the image file
        return send_file(
            qr_image,
            mimetype='image/png',
            as_attachment=True,
            download_name=f'qr-code-{size}x{size}.png'
        )
    
    except ValueError as ve:
        return jsonify({'error': f'Invalid parameter: {str(ve)}'}), 400
    except Exception as e:
        print(f"Error generating QR code: {str(e)}")
        return jsonify({'error': 'Failed to generate QR code', 'details': str(e)}), 500
