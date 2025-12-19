# Image routes - Endpoints for image processing operations
from flask import Blueprint, request, send_file, jsonify
import io
import os
import zipfile
from werkzeug.utils import secure_filename
from PIL import UnidentifiedImageError
from services.image_service import (
    compress_image_bytes, ext_of_filename, is_image_ext, 
    ALLOWED_INPUT_EXTS, ALLOWED_IMAGE_EXTS, HEIC_AVAILABLE
)

image_bp = Blueprint("image", __name__)


@image_bp.route("/img-compress", methods=["POST", "OPTIONS"])
def img_compress():
    """
    POST form-data:
      - file: single image file (.png/.webp/.jpg/.jpeg/.bmp/.gif/.tiff/.heic/.heif) or .zip containing images
      - quality: integer 1..100 (optional, default 85 for lossy formats)
    
    Returns:
      - Single compressed image if single image uploaded
      - ZIP file with compressed images if ZIP file uploaded
    """
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
        
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    upload = request.files["file"]
    filename = secure_filename(upload.filename or "upload")
    if filename == "":
        return jsonify({"error": "Empty filename"}), 400

    # Get quality parameter (1-100)
    try:
        quality = int(request.form.get("quality", 85))
        quality = max(1, min(100, quality))
    except Exception:
        quality = 85

    incoming_ext = ext_of_filename(filename)
    if incoming_ext not in ALLOWED_INPUT_EXTS:
        return jsonify({"error": f"Unsupported input extension: {incoming_ext}"}), 400

    # Single image file (not zip)
    if incoming_ext != ".zip":
        if incoming_ext in ('.heic', '.heif') and not HEIC_AVAILABLE:
            return jsonify({
                "error": "HEIC/HEIF support is not enabled on the server. "
                         "Install the optional 'pillow-heif' package and native libheif (see docs)."
            }), 400

        in_bytes = upload.read()
        try:
            compressed_bytes, mimetype, out_ext = compress_image_bytes(in_bytes, incoming_ext, quality=quality)
        except UnidentifiedImageError:
            return jsonify({"error": "Uploaded file is not a recognized image"}), 400
        except Exception as e:
            return jsonify({"error": f"Image compression failed: {str(e)}"}), 500

        base = os.path.splitext(filename)[0]
        out_name = f"{base}_compressed{out_ext}"
        return send_file(
            io.BytesIO(compressed_bytes),
            as_attachment=True,
            download_name=out_name,
            mimetype=mimetype
        )

    # If ZIP -> extract, compress all supported images inside, return zip
    zip_bytes = upload.read()
    in_zip = io.BytesIO(zip_bytes)
    out_zip_io = io.BytesIO()
    
    with zipfile.ZipFile(in_zip, "r") as zin, zipfile.ZipFile(out_zip_io, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        file_list = zin.namelist()
        if not file_list:
            return jsonify({"error": "Zip contains no files"}), 400

        processed_any = False
        skipped_heic = False
        
        for member in file_list:
            if member.endswith("/"):
                continue
            member_name = os.path.basename(member)
            if not member_name:
                continue
            ext = ext_of_filename(member_name)
            
            try:
                raw = zin.read(member)
            except Exception:
                continue

            if ext in ('.heic', '.heif') and not HEIC_AVAILABLE:
                skipped_heic = True
                continue

            if is_image_ext(ext):
                try:
                    compressed_bytes, _, out_ext = compress_image_bytes(raw, ext, quality=quality)
                except UnidentifiedImageError:
                    continue
                except Exception:
                    continue
                    
                base = os.path.splitext(member_name)[0]
                new_name = f"{base}_compressed{out_ext}"
                zout.writestr(new_name, compressed_bytes)
                processed_any = True
            else:
                continue

        if not processed_any:
            if skipped_heic:
                return jsonify({
                    "error": "No images were compressed. The ZIP contains HEIC/HEIF images but the server "
                             "is missing HEIC support. Install 'pillow-heif' and native 'libheif' to enable HEIC support."
                }), 400
            return jsonify({"error": "No supported images found inside zip"}), 400

    out_zip_io.seek(0)
    base_in_zip = os.path.splitext(filename)[0]
    out_zip_name = f"{base_in_zip}_compressed.zip"
    return send_file(
        out_zip_io,
        as_attachment=True,
        download_name=out_zip_name,
        mimetype="application/zip"
    )


# Import and wrap other image endpoints from existing files
# These will keep their original logic intact
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Lazy loading for heavy endpoint modules - imported only when endpoints are called
# This reduces startup memory footprint

# Wrap the existing functions to keep them in this blueprint
@image_bp.route("/img-jpg", methods=["POST", "OPTIONS"])
def img_jpg():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from imgtojpg import img_to_jpg as _img_to_jpg_original
    return _img_to_jpg_original()


@image_bp.route("/img-png", methods=["POST", "OPTIONS"])
def img_png():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from imgtopng import img_to_png as _img_to_png_original
    return _img_to_png_original()


@image_bp.route("/img-webp", methods=["POST", "OPTIONS"])
def img_webp():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from imgtowebp import img_webp as _img_webp_original
    return _img_webp_original()


@image_bp.route("/upscale", methods=["POST", "OPTIONS"])
def upscale():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from upscaleimg import upscale_zip_or_image as _upscale_original
    return _upscale_original()


@image_bp.route("/remove-imgbg", methods=["POST", "OPTIONS"])
def remove_imgbg():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from removeimgbg import remove_imgbg_endpoint as _remove_bg_original
    return _remove_bg_original()


@image_bp.route("/watermark-imgvideo", methods=["POST", "OPTIONS"])
def watermark_imgvideo():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from watermarkimgvideo import watermark_imgvideo_endpoint as _watermark_original
    return _watermark_original()
