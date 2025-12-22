import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer, SquareModuleDrawer
from io import BytesIO
from PIL import Image, ImageDraw


def generate_qr_code(data, size=300, error_correction='M', foreground='#000000', background='#ffffff'):
    """
    Generate a QR code image with customization options.
    
    Args:
        data (str): The data to encode in the QR code
        size (int): Size of the QR code in pixels (default: 300)
        error_correction (str): Error correction level - 'L', 'M', 'Q', or 'H' (default: 'M')
        foreground (str): Foreground color in hex format (default: '#000000')
        background (str): Background color in hex format (default: '#ffffff')
    
    Returns:
        BytesIO: QR code image as a BytesIO object
    """
    # Map error correction levels
    error_correction_map = {
        'L': qrcode.constants.ERROR_CORRECT_L,  # 7%
        'M': qrcode.constants.ERROR_CORRECT_M,  # 15%
        'Q': qrcode.constants.ERROR_CORRECT_Q,  # 25%
        'H': qrcode.constants.ERROR_CORRECT_H   # 30%
    }
    
    # Get error correction level
    ec_level = error_correction_map.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M)
    
    # Create QR Code instance
    qr = qrcode.QRCode(
        version=1,  # Auto-adjust version based on data
        error_correction=ec_level,
        box_size=10,
        border=4,
    )
    
    # Add data to QR code
    qr.add_data(data)
    qr.make(fit=True)
    
    # Create image with custom colors
    img = qr.make_image(fill_color=foreground, back_color=background)
    
    # Resize to requested size
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    
    # Save to BytesIO
    img_io = BytesIO()
    img.save(img_io, 'PNG', quality=95)
    img_io.seek(0)
    
    return img_io


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
