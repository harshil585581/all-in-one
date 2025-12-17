# imgtowebp.py
import os
import io
import zipfile
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError

# Optional HEIC support
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except Exception:
    HEIF_AVAILABLE = False

ALLOWED_EXTS = {'.png', '.webp', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.tif', '.heic', '.heif'}

app = Flask(__name__)

# Configure CORS explicitly. Change origins if you want more restriction.
CORS(app, resources={r"/img-webp": {"origins": ["http://localhost:4200", "http://127.0.0.1:4200"]}})

def allowed_filename(filename: str):
    ext = os.path.splitext(filename.lower())[1]
    return ext in ALLOWED_EXTS or ext == '.zip'

def convert_image_to_webp_bytes(in_bytes: bytes, convert_quality: int = 80) -> bytes:
    """
    Convert raw image bytes to webp bytes. Returns bytes.
    """
    with Image.open(io.BytesIO(in_bytes)) as img:
        # Preserve transparency if present
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and 'transparency' in img.info):
            out = io.BytesIO()
            img.save(out, format='WEBP', quality=convert_quality, lossless=False, method=6)
            out.seek(0)
            return out.read()
        else:
            rgb = img.convert("RGB")
            out = io.BytesIO()
            rgb.save(out, format='WEBP', quality=convert_quality, method=6)
            out.seek(0)
            return out.read()

@app.route('/img-webp', methods=['POST', 'OPTIONS'])
def img_webp():
    if request.method == 'OPTIONS':
        # Flask-CORS usually handles OPTIONS automatically, but keep safe fallback
        return ('', 204)

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    filename = secure_filename(file.filename or 'file')
    if filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    try:
        quality = int(request.form.get('quality', 80))
    except Exception:
        quality = 80
    quality = max(0, min(100, quality))

    name_lower = filename.lower()
    is_zip = name_lower.endswith('.zip')

    # Single image path
    if not is_zip:
        if not allowed_filename(filename):
            return jsonify({'error': 'Unsupported file type'}), 400

        content = file.read()
        try:
            webp_bytes = convert_image_to_webp_bytes(content, convert_quality=quality)
        except UnidentifiedImageError:
            return jsonify({'error': 'Could not identify image file (Unsupported or corrupted)'}), 400
        except Exception as e:
            return jsonify({'error': f'Conversion failed: {str(e)}'}), 500

        out_name = os.path.splitext(filename)[0] + '.webp'
        return send_file(
            io.BytesIO(webp_bytes),
            as_attachment=True,
            download_name=out_name,
            mimetype='image/webp'
        )

    # ZIP path — use in-memory BytesIO to avoid Windows file-lock issues
    try:
        zip_bytes = file.read()
        in_zip = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return jsonify({'error': 'Invalid ZIP file'}), 400

    out_buffer = io.BytesIO()
    with zipfile.ZipFile(out_buffer, 'w', zipfile.ZIP_DEFLATED) as out_zip:
        any_converted = False
        for member in in_zip.infolist():
            if member.is_dir():
                continue
            inner_name = member.filename
            ext = os.path.splitext(inner_name.lower())[1]
            if ext not in ALLOWED_EXTS:
                # skip non-supported files
                continue
            try:
                with in_zip.open(member) as f:
                    img_bytes = f.read()
                webp_bytes = convert_image_to_webp_bytes(img_bytes, convert_quality=quality)
                base = os.path.splitext(inner_name)[0]
                out_name = base + '.webp'
                out_zip.writestr(out_name, webp_bytes)
                any_converted = True
            except UnidentifiedImageError:
                # skip corrupted/unidentified images
                continue
            except Exception:
                # skip problematic entries but continue others
                continue

    if not any_converted:
        return jsonify({'error': 'No supported images found in ZIP'}), 400

    out_buffer.seek(0)
    download_name = os.path.splitext(filename)[0] + '_webp.zip'
    return send_file(
        out_buffer,
        as_attachment=True,
        download_name=download_name,
        mimetype='application/zip'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
