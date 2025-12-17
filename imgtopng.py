# app.py
import io
import zipfile
import tempfile
import os
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Allowed image extensions (case-insensitive)
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.heif', '.heic', '.jfif'}

def is_image_filename(name: str) -> bool:
    _, ext = os.path.splitext(name.lower())
    return ext in IMAGE_EXTS

def convert_image_fileobj_to_png_bytes(fileobj) -> bytes:
    """
    Given a file-like object containing an image, return PNG bytes.
    Will convert palette/animated images to first frame.
    """
    with Image.open(fileobj) as im:
        # Convert animated GIFs/WebPs to first frame and ensure RGBA/RGB as needed
        try:
            im.seek(0)
        except Exception:
            pass
        # Convert mode to RGBA or RGB to preserve alpha if present
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and 'transparency' in im.info):
            out_mode = "RGBA"
        elif im.mode == "P":
            out_mode = "RGB"
        else:
            out_mode = im.mode if im.mode in ("RGB","RGBA","L") else "RGB"
        converted = im.convert(out_mode)
        out_bytes = io.BytesIO()
        # Save as PNG
        converted.save(out_bytes, format="PNG", optimize=True)
        out_bytes.seek(0)
        return out_bytes.read()

@app.route('/img-png', methods=['POST'])
def img_to_png():
    """
    Accepts multipart/form-data with key 'file'.
    If single image -> returns image/png with filename <originalname>.png
    If zip -> returns zip file (application/zip) containing converted PNGs
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    filename = secure_filename(file.filename)
    lower = filename.lower()

    try:
        # If a zip file was uploaded -> iterate entries and convert each image
        if lower.endswith('.zip'):
            # Read zip into memory (stream)
            z_in = zipfile.ZipFile(file.stream)
            # Prepare output zip in memory
            out_io = io.BytesIO()
            with zipfile.ZipFile(out_io, mode='w', compression=zipfile.ZIP_DEFLATED) as zout:
                for member in z_in.infolist():
                    # skip directories
                    if member.is_dir():
                        continue
                    name = member.filename
                    # normalize
                    base_name = os.path.basename(name)
                    if not base_name:
                        continue
                    if not is_image_filename(base_name):
                        # skip non-images
                        continue
                    try:
                        with z_in.open(member) as entry_file:
                            img_bytes = convert_image_fileobj_to_png_bytes(entry_file)
                            out_name = os.path.splitext(base_name)[0] + '.png'
                            zout.writestr(out_name, img_bytes)
                    except UnidentifiedImageError:
                        # skip unrecognized images
                        continue
                    except Exception as e:
                        # skip problematic files but continue
                        continue
            out_io.seek(0)
            resp_name = os.path.splitext(filename)[0] + '_pngs.zip'
            return send_file(
                out_io,
                mimetype='application/zip',
                as_attachment=True,
                download_name=resp_name
            )

        # Not a zip: expect single file. Check if it's an image
        if not is_image_filename(filename):
            return jsonify({'error': 'Uploaded file is not a supported image type or zip'}), 400

        # Convert single image
        # Use file.stream which is file-like
        try:
            png_bytes = convert_image_fileobj_to_png_bytes(file.stream)
        except UnidentifiedImageError:
            return jsonify({'error': 'Could not identify image format'}), 400

        out_io = io.BytesIO(png_bytes)
        out_io.seek(0)
        resp_name = os.path.splitext(filename)[0] + '.png'
        return send_file(
            out_io,
            mimetype='image/png',
            as_attachment=True,
            download_name=resp_name
        )

    except zipfile.BadZipFile:
        return jsonify({'error': 'Invalid ZIP file'}), 400
    except Exception as e:
        # log in real app
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 500

if __name__ == '__main__':
    # For development only. Use gunicorn/uvicorn behind a reverse proxy in production.
    app.run(host='0.0.0.0', port=5000, debug=True)
