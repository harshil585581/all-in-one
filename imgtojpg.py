# app.py
import io
import os
import zipfile
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError

# Try to enable HEIC/HEIF support via pillow-heif (optional).
# If pillow-heif is installed, register its opener so Pillow can open .heic/.heif files.
HEIC_AVAILABLE = False
try:
    import pillow_heif
    pillow_heif.register_heif_opener()  # register opener with Pillow
    HEIC_AVAILABLE = True
except Exception:
    # Not fatal — server still works for other formats.
    HEIC_AVAILABLE = False

# Supported image extensions (lowercase)
ALLOWED_IMAGE_EXTS = {
    '.png', '.webp', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.tif', '.heic', '.heif'
}
ALLOWED_INPUT_EXTS = ALLOWED_IMAGE_EXTS.union({'.zip'})

app = Flask(__name__)
CORS(app)


def ext_of_filename(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def is_image_ext(ext: str) -> bool:
    return ext in ALLOWED_IMAGE_EXTS


def convert_image_to_jpeg_bytes(file_bytes: bytes, out_ext: str = '.jpg', quality: int = 85) -> bytes:
    """
    Convert arbitrary image bytes to JPEG bytes.
    Handles alpha channels by compositing onto white.
    Raises UnidentifiedImageError if PIL cannot open the bytes.
    """
    with Image.open(io.BytesIO(file_bytes)) as im:
        # For HEIC/HEIF with multiple pages/frames, Pillow via pillow-heif gives the first frame
        # For animated GIFs, take the first frame
        if getattr(im, "is_animated", False):
            try:
                im = im.convert("RGBA")
            except Exception:
                im = im.copy().convert("RGBA")

        # Convert to RGB and handle alpha by compositing onto white background
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            try:
                bg.paste(im, mask=im.split()[-1])  # use alpha channel as mask
            except Exception:
                bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
            out_im = bg
        else:
            out_im = im.convert("RGB")

        out_buf = io.BytesIO()
        out_im.save(out_buf, format="JPEG", quality=quality, optimize=True)
        out_buf.seek(0)
        return out_buf.read()


@app.route("/img-jpg", methods=["POST", "OPTIONS"])
def img_to_jpg():
    """
    POST form-data:
      - file: single file (.png/.webp/... or .zip)
      - format: 'jpg' or 'jpeg' (optional, default 'jpg')
      - quality: integer 1..95 (optional)
    """
    # Handle OPTIONS preflight request
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    upload = request.files["file"]
    filename = secure_filename(upload.filename or "upload")
    if filename == "":
        return jsonify({"error": "Empty filename"}), 400

    requested_format = (request.form.get("format") or "jpg").lower()
    if requested_format not in ("jpg", "jpeg"):
        requested_format = "jpg"
    out_ext = "." + requested_format

    try:
        quality = int(request.form.get("quality", 85))
        quality = max(1, min(95, quality))
    except Exception:
        quality = 85

    incoming_ext = ext_of_filename(filename)
    if incoming_ext not in ALLOWED_INPUT_EXTS:
        return jsonify({"error": f"Unsupported input extension: {incoming_ext}"}), 400

    # Single image file (not zip)
    if incoming_ext != ".zip":
        # If the file is HEIC/HEIF but pillow-heif not available, return helpful message
        if incoming_ext in ('.heic', '.heif') and not HEIC_AVAILABLE:
            return jsonify({
                "error": "HEIC/HEIF support is not enabled on the server. "
                         "Install the optional 'pillow-heif' package and native libheif (see docs)."
            }), 400

        in_bytes = upload.read()
        try:
            converted = convert_image_to_jpeg_bytes(in_bytes, out_ext=out_ext, quality=quality)
        except UnidentifiedImageError:
            return jsonify({"error": "Uploaded file is not a recognized image"}), 400
        except Exception as e:
            return jsonify({"error": f"Image conversion failed: {str(e)}"}), 500

        base = os.path.splitext(filename)[0]
        out_name = f"{base}{out_ext}"
        return send_file(
            io.BytesIO(converted),
            as_attachment=True,
            download_name=out_name,
            mimetype="image/jpeg"
        )

    # If ZIP -> extract, convert all supported images inside, return zip
    zip_bytes = upload.read()
    in_zip = io.BytesIO(zip_bytes)
    out_zip_io = io.BytesIO()
    with zipfile.ZipFile(in_zip, "r") as zin, zipfile.ZipFile(out_zip_io, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        file_list = zin.namelist()
        if not file_list:
            return jsonify({"error": "Zip contains no files"}), 400

        processed_any = False
        for member in file_list:
            # ignore directories
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

            # If file is HEIC/HEIF and pillow-heif not available -> skip and later return helpful error
            if ext in ('.heic', '.heif') and not HEIC_AVAILABLE:
                # skip but mark that HEIC files were found
                # We'll gather at least one processed_any to allow partial success if other images exist
                # But at the end, if processed_any is False, return error explaining HEIC support missing.
                continue

            if is_image_ext(ext):
                try:
                    converted_bytes = convert_image_to_jpeg_bytes(raw, out_ext=out_ext, quality=quality)
                except UnidentifiedImageError:
                    # skip files that aren't recognized as images
                    continue
                except Exception:
                    continue
                base = os.path.splitext(member_name)[0]
                new_name = base + out_ext
                zout.writestr(new_name, converted_bytes)
                processed_any = True
            else:
                # skip non-image files
                continue

        if not processed_any:
            # If none processed, inspect whether zip contained any HEIC files but pillow-heif not available
            contains_heic = any(
                ext_of_filename(os.path.basename(m)) in ('.heic', '.heif') for m in file_list if not m.endswith('/')
            )
            if contains_heic and not HEIC_AVAILABLE:
                return jsonify({
                    "error": "No images were converted. The ZIP contains HEIC/HEIF images but the server "
                             "is missing HEIC support. Install 'pillow-heif' and native 'libheif' to enable HEIC support."
                }), 400
            return jsonify({"error": "No supported images found inside zip"}), 400

    out_zip_io.seek(0)
    base_in_zip = os.path.splitext(filename)[0]
    out_zip_name = f"{base_in_zip}_jpgs.zip"
    return send_file(
        out_zip_io,
        as_attachment=True,
        download_name=out_zip_name,
        mimetype="application/zip"
    )


if __name__ == "__main__":
    # debug True is helpful locally; disable in production
    app.run(host="0.0.0.0", port=5000, debug=True)
