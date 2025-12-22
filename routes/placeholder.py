# Placeholder image generator routes - Endpoint for generating custom placeholder images
from flask import Blueprint, request, send_file, jsonify
from PIL import Image, ImageDraw, ImageFont
import io
import os

placeholder_bp = Blueprint("placeholder", __name__)


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


@placeholder_bp.route('/generate-placeholder', methods=['POST', 'OPTIONS'])
def generate_placeholder():
    """Generate a placeholder image with custom dimensions and styling."""
    
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        
        # Extract and validate parameters
        width = int(data.get('width', 600))
        height = int(data.get('height', 400))
        img_format = data.get('format', 'png').lower()
        bg_color = data.get('background_color', '#cccccc')
        text_color = data.get('text_color', '#333333')
        text = data.get('text', f'{width}×{height}')
        font_size = int(data.get('font_size', 48))
        
        # Validate dimensions
        if width < 1 or width > 4000:
            return jsonify({'error': 'Width must be between 1 and 4000 pixels'}), 400
        if height < 1 or height > 4000:
            return jsonify({'error': 'Height must be between 1 and 4000 pixels'}), 400
        
        # Validate format
        if img_format not in ['png', 'jpg', 'jpeg', 'webp']:
            return jsonify({'error': 'Format must be png, jpg, or webp'}), 400
        
        # Convert hex colors to RGB
        bg_rgb = hex_to_rgb(bg_color)
        text_rgb = hex_to_rgb(text_color)
        
        # Create image with background color
        image = Image.new('RGB', (width, height), bg_rgb)
        draw = ImageDraw.Draw(image)
        
        # Try to use a system font, fallback to default if not available
        try:
            # Try different font paths based on OS
            font_paths = [
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',  # Linux
                '/System/Library/Fonts/Helvetica.ttc',  # macOS
                'C:\\Windows\\Fonts\\arial.ttf',  # Windows
                'arial.ttf',  # Fallback
            ]
            
            font = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, font_size)
                    break
            
            if font is None:
                # Use default font if no TrueType font found
                font = ImageFont.load_default()
        except Exception:
            # Fallback to default font
            font = ImageFont.load_default()
        
        # Calculate text position (center)
        # Use textbbox for accurate text dimensions
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        position = (
            (width - text_width) // 2,
            (height - text_height) // 2
        )
        
        # Draw text on image
        draw.text(position, text, fill=text_rgb, font=font)
        
        # Save image to bytes buffer
        img_buffer = io.BytesIO()
        
        # Normalize format name
        save_format = 'JPEG' if img_format in ['jpg', 'jpeg'] else img_format.upper()
        
        # Save with appropriate format
        if save_format == 'JPEG':
            image.save(img_buffer, format=save_format, quality=95)
        else:
            image.save(img_buffer, format=save_format)
        
        img_buffer.seek(0)
        
        # Determine MIME type
        mime_types = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'webp': 'image/webp'
        }
        mime_type = mime_types.get(img_format, 'image/png')
        
        # Return image
        return send_file(
            img_buffer,
            mimetype=mime_type,
            as_attachment=False,
            download_name=f'placeholder_{width}x{height}.{img_format}'
        )
        
    except ValueError as e:
        return jsonify({'error': f'Invalid parameter value: {str(e)}'}), 400
    except Exception as e:
        print(f'Error generating placeholder: {str(e)}')
        return jsonify({'error': 'Failed to generate placeholder image'}), 500
