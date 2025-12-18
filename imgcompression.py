# imgcompression.py
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
    """Extract file extension in lowercase."""
    return os.path.splitext(name)[1].lower()


def is_image_ext(ext: str) -> bool:
    """Check if extension is a supported image format."""
    return ext in ALLOWED_IMAGE_EXTS


def compress_image_bytes(file_bytes: bytes, original_ext: str, quality: int = 85) -> tuple[bytes, str, str]:
    """
    Compress image bytes while preserving the original format.
    Returns (compressed_bytes, mimetype, out_ext).
    Applies quality-based compression for all formats.
    Quality: 10-95, lower = smaller file size but lower visual quality.
    """
    with Image.open(io.BytesIO(file_bytes)) as im:
        # For animated GIFs, take the first frame
        if getattr(im, "is_animated", False):
            try:
                im.seek(0)
                im = im.copy()
            except Exception:
                pass

        out_buf = io.BytesIO()
        
        # Determine output format based on original extension
        if original_ext in ['.png']:
            # PNG: Apply quality through color quantization for smaller files
            # Quality mapping: 10-95 -> color count reduction
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                # Preserve alpha channel for PNG
                if im.mode == "P":
                    im = im.convert("RGBA")
                
                # Apply color quantization based on quality
                # Higher quality = more colors, lower quality = fewer colors
                if quality < 95:
                    # Map quality 10-95 to colors 16-256
                    max_colors = int(16 + (quality / 95.0) * 240)
                    # Quantize to reduce color palette
                    im = im.quantize(colors=max_colors, method=2).convert("RGBA")
                
                im.save(out_buf, format="PNG", optimize=True, compress_level=9)
            else:
                # Convert to RGB and apply quantization
                rgb_im = im.convert("RGB")
                
                if quality < 95:
                    max_colors = int(16 + (quality / 95.0) * 240)
                    # Quantize and convert back to RGB
                    rgb_im = rgb_im.quantize(colors=max_colors, method=2).convert("RGB")
                
                rgb_im.save(out_buf, format="PNG", optimize=True, compress_level=9)
            mimetype = "image/png"
            out_ext = ".png"
            
        elif original_ext in ['.webp']:
            # WebP: supports both lossy and transparency
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                # Preserve transparency for WebP
                if im.mode == "P":
                    im = im.convert("RGBA")
                im.save(out_buf, format="WEBP", quality=quality, method=6, lossless=False)
            else:
                rgb_im = im.convert("RGB")
                rgb_im.save(out_buf, format="WEBP", quality=quality, method=6, lossless=False)
            mimetype = "image/webp"
            out_ext = ".webp"
            
        elif original_ext in ['.jpg', '.jpeg']:
            # JPEG: no alpha support, convert to RGB and apply quality
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                # Composite onto white background
                bg = Image.new("RGB", im.size, (255, 255, 255))
                try:
                    bg.paste(im, mask=im.split()[-1])
                except Exception:
                    bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                out_im = bg
            else:
                out_im = im.convert("RGB")
            out_im.save(out_buf, format="JPEG", quality=quality, optimize=True, subsampling=0 if quality >= 90 else 2)
            mimetype = "image/jpeg"
            out_ext = ".jpg"
            
        elif original_ext in ['.bmp']:
            # BMP: Convert to JPEG with quality control for compression
            # Since BMP doesn't support quality, we convert to JPEG
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                try:
                    bg.paste(im, mask=im.split()[-1])
                except Exception:
                    bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                out_im = bg
            else:
                out_im = im.convert("RGB")
            # Save as JPEG with quality for better compression
            out_im.save(out_buf, format="JPEG", quality=quality, optimize=True)
            mimetype = "image/jpeg"
            out_ext = ".jpg"  # BMP compressed to JPG
            
        elif original_ext in ['.gif']:
            # GIF: Apply quality through color reduction
            if quality < 95:
                # Map quality to color count (8-256 colors)
                max_colors = int(8 + (quality / 95.0) * 248)
                if im.mode != "P":
                    # Convert to palette mode with limited colors
                    im = im.convert("RGB").quantize(colors=max_colors, method=2)
                else:
                    # Re-quantize existing palette
                    im = im.convert("RGB").quantize(colors=max_colors, method=2)
            
            im.save(out_buf, format="GIF", optimize=True, save_all=False)
            mimetype = "image/gif"
            out_ext = ".gif"
            
        elif original_ext in ['.tiff', '.tif']:
            # TIFF: Convert to JPEG with quality control
            # TIFF with LZW is lossless, so convert to JPEG for size control
            if im.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                try:
                    bg.paste(im, mask=im.split()[-1])
                except Exception:
                    bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                out_im = bg
            else:
                out_im = im.convert("RGB")
            out_im.save(out_buf, format="JPEG", quality=quality, optimize=True)
            mimetype = "image/jpeg"
            out_ext = ".jpg"  # TIFF compressed to JPG
            
        elif original_ext in ['.heic', '.heif']:
            # HEIC/HEIF: convert to JPEG with quality control
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                try:
                    bg.paste(im, mask=im.split()[-1])
                except Exception:
                    bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                out_im = bg
            else:
                out_im = im.convert("RGB")
            out_im.save(out_buf, format="JPEG", quality=quality, optimize=True)
            mimetype = "image/jpeg"
            out_ext = ".jpg"
        else:
            # Default: convert to JPEG with quality
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                try:
                    bg.paste(im, mask=im.split()[-1])
                except Exception:
                    bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                out_im = bg
            else:
                out_im = im.convert("RGB")
            out_im.save(out_buf, format="JPEG", quality=quality, optimize=True)
            mimetype = "image/jpeg"
            out_ext = ".jpg"

        out_buf.seek(0)
        return out_buf.read(), mimetype, out_ext


@app.route("/img-compress", methods=["POST", "OPTIONS"])
def img_compress():
    """
    POST form-data:
      - file: single image file (.png/.webp/.jpg/.jpeg/.bmp/.gif/.tiff/.heic/.heif) or .zip containing images
      - quality: integer 1..100 (optional, default 85 for lossy formats)
    
    Returns:
      - Single compressed image if single image uploaded
      - ZIP file with compressed images if ZIP file uploaded
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
        # If the file is HEIC/HEIF but pillow-heif not available, return helpful message
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

            # If file is HEIC/HEIF and pillow-heif not available -> skip
            if ext in ('.heic', '.heif') and not HEIC_AVAILABLE:
                skipped_heic = True
                continue

            if is_image_ext(ext):
                try:
                    compressed_bytes, _, out_ext = compress_image_bytes(raw, ext, quality=quality)
                except UnidentifiedImageError:
                    # skip files that aren't recognized as images
                    continue
                except Exception:
                    continue
                    
                base = os.path.splitext(member_name)[0]
                new_name = f"{base}_compressed{out_ext}"
                zout.writestr(new_name, compressed_bytes)
                processed_any = True
            else:
                # skip non-image files
                continue

        if not processed_any:
            # If none processed, check if it's because of HEIC files
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


if __name__ == "__main__":
    # debug True is helpful locally; disable in production
    app.run(host="0.0.0.0", port=5000, debug=True)
