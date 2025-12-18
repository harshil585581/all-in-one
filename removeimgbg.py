# removeimgbg.py
import os
import io
import zipfile
import traceback
import tempfile
import shutil
from pathlib import Path
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from PIL import Image
from rembg import remove
from pillow_heif import register_heif_opener

# Register HEIF/HEIC support for PIL
register_heif_opener()

app = Flask(__name__)

# CORS configuration
CORS(app, resources={r"/*": {
    "origins": "*",
    "allow_headers": "*",
    "expose_headers": "*",
    "methods": ["GET", "POST", "OPTIONS"],
}}, supports_credentials=False)

app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

# Supported image formats with their PIL format names
SUPPORTED_FORMATS = {
    '.jpg': 'JPEG',
    '.jpeg': 'JPEG',
    '.png': 'PNG',
    '.webp': 'WEBP',
    '.gif': 'GIF',
    '.bmp': 'BMP',
    '.tiff': 'TIFF',
    '.tif': 'TIFF',
    '.heic': 'PNG',  # Convert HEIC to PNG
    '.heif': 'PNG'   # Convert HEIF to PNG
}


def is_image_filename(name: str) -> bool:
    """Check if filename has a supported image extension."""
    ext = Path(name).suffix.lower()
    return ext in SUPPORTED_FORMATS


def get_image_format(filename):
    """Extract the image format from filename extension."""
    ext = Path(filename).suffix.lower()
    return SUPPORTED_FORMATS.get(ext, 'PNG')


def remove_background_preserve_format(image_path, original_filename):
    """
    Remove background from image and return in original format.
    
    Args:
        image_path: Path to the image file
        original_filename: Original filename to determine format
    
    Returns:
        tuple: (output_path, format_name, output_extension)
    """
    # Open image
    with Image.open(image_path) as img:
        print(f"  Opened: {img.size}, mode: {img.mode}")
        
        # Convert to RGB if needed (rembg needs RGB/RGBA)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        
        # Remove background using rembg
        result = remove(img)
        print(f"  Background removed, result mode: {result.mode}")
    
    # Determine original format
    original_format = get_image_format(original_filename)
    original_ext = Path(original_filename).suffix.lower()
    
    # Convert RGBA to RGB for formats that don't support transparency
    if original_format in ['JPEG', 'BMP'] and result.mode == 'RGBA':
        print(f"  Converting RGBA to RGB with white background for {original_format}")
        # Create white background
        background = Image.new('RGB', result.size, (255, 255, 255))
        background.paste(result, mask=result.split()[3])  # Use alpha channel as mask
        result = background
    
    # Create output filename with original extension
    base_name = Path(original_filename).stem
    output_filename = f"{base_name}_nobg{original_ext}"
    
    return result, original_format, output_filename


@app.get("/")
def index():
    return jsonify({"status": "ok", "note": "Remove Image Background API running"})


@app.route("/remove-imgbg", methods=['POST', 'OPTIONS'])
def remove_imgbg_endpoint():
    """
    Endpoint to remove background from images.
    Preserves original file formats.
    - Single image upload: returns image in original format
    - ZIP file upload: returns ZIP with all processed images in their original formats
    """
    # Handle OPTIONS preflight request
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    
    print("---- /remove-imgbg HIT ----")
    temp_root = None
    
    try:
        # Check file presence
        if "file" not in request.files:
            print("❌ ERROR: No file found in request")
            return jsonify({"error": "No file uploaded"}), 400

        uploaded = request.files["file"]
        filename = uploaded.filename or "uploaded"
        print("Uploaded filename:", filename, "mimetype:", uploaded.mimetype)

        # Create temp directory
        temp_root = tempfile.mkdtemp(prefix="remove_bg_")
        print("Temp directory:", temp_root)

        input_dir = os.path.join(temp_root, "input")
        output_dir = os.path.join(temp_root, "output")
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        # Save uploaded file to disk
        uploaded_path = os.path.join(temp_root, filename)
        uploaded.save(uploaded_path)
        print("Saved uploaded file at:", uploaded_path)

        processed_files = []
        is_zip_upload = False

        # Check if uploaded file is a ZIP
        if filename.lower().endswith(".zip") or uploaded.mimetype == "application/zip":
            is_zip_upload = True
            print("Processing ZIP file...")
            
            try:
                # Validate ZIP file
                with zipfile.ZipFile(uploaded_path, "r") as ztest:
                    test = ztest.testzip()
                    if test is not None:
                        print("❌ zip.testzip flagged bad member:", test)
                        return jsonify({"error": "ZIP file appears corrupted"}), 400
            except zipfile.BadZipFile as bz:
                print("❌ BadZipFile:", bz)
                return jsonify({"error": "Uploaded file is not a valid ZIP file"}), 400

            # Extract ZIP
            try:
                with zipfile.ZipFile(uploaded_path, "r") as z:
                    print("ZIP entries:", z.namelist())
                    z.extractall(input_dir)
            except Exception as e:
                print("❌ ZIP EXTRACT ERROR:", e)
                raise

            # Process all images in ZIP (including nested folders)
            for root, dirs, files in os.walk(input_dir):
                for fname in files:
                    if not is_image_filename(fname):
                        print(f"Skipping non-image: {fname}")
                        continue
                    
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, input_dir)
                    
                    try:
                        print(f"Processing image: {rel_path}")
                        
                        # Remove background and preserve format
                        result_img, img_format, output_filename = remove_background_preserve_format(
                            fpath, fname
                        )
                        
                        # Save with appropriate format
                        out_path = os.path.join(output_dir, output_filename)
                        
                        # Save with format-specific settings
                        if img_format == 'JPEG':
                            result_img.save(out_path, 'JPEG', quality=95)
                        elif img_format == 'WEBP':
                            result_img.save(out_path, 'WEBP', quality=95)
                        elif img_format == 'PNG':
                            result_img.save(out_path, 'PNG')
                        elif img_format == 'GIF':
                            result_img.save(out_path, 'GIF')
                        elif img_format == 'BMP':
                            result_img.save(out_path, 'BMP')
                        elif img_format == 'TIFF':
                            result_img.save(out_path, 'TIFF')
                        else:
                            result_img.save(out_path, 'PNG')
                        
                        print(f"  Saved: {output_filename} (format: {img_format})")
                        processed_files.append(output_filename)
                        
                    except Exception as e:
                        print(f"❌ IMAGE PROCESS ERROR for {rel_path}: {e}")
                        traceback.print_exc()

        # Single image upload
        elif uploaded.mimetype and uploaded.mimetype.startswith("image") or is_image_filename(filename):
            print("Processing single image...")
            
            try:
                # Remove background and preserve format
                result_img, img_format, output_filename = remove_background_preserve_format(
                    uploaded_path, filename
                )
                
                # Save with appropriate format
                out_path = os.path.join(output_dir, output_filename)
                
                # Save with format-specific settings
                if img_format == 'JPEG':
                    result_img.save(out_path, 'JPEG', quality=95)
                elif img_format == 'WEBP':
                    result_img.save(out_path, 'WEBP', quality=95)
                elif img_format == 'PNG':
                    result_img.save(out_path, 'PNG')
                elif img_format == 'GIF':
                    result_img.save(out_path, 'GIF')
                elif img_format == 'BMP':
                    result_img.save(out_path, 'BMP')
                elif img_format == 'TIFF':
                    result_img.save(out_path, 'TIFF')
                else:
                    result_img.save(out_path, 'PNG')
                
                print(f"Saved: {output_filename} (format: {img_format})")
                processed_files.append(output_filename)
                
            except Exception as e:
                print(f"❌ IMAGE PROCESS ERROR for {filename}: {e}")
                traceback.print_exc()
                return jsonify({"error": f"Failed to process image: {str(e)}"}), 400
        
        else:
            print("❌ Unsupported uploaded file type:", filename, uploaded.mimetype)
            return jsonify({"error": "Uploaded file must be a ZIP containing images or a single image file."}), 400

        # Check if any files were processed
        if not processed_files:
            return jsonify({"error": "No valid image files were processed. Supported formats: jpg, jpeg, png, webp, heic, heif, gif, bmp, tiff"}), 400

        # If ZIP upload or multiple files processed, return ZIP
        if is_zip_upload or len(processed_files) > 1:
            print("Creating output ZIP...")
            output_zip_path = os.path.join(temp_root, "images_nobg.zip")
            
            with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for out_file in sorted(processed_files):
                    file_path = os.path.join(output_dir, out_file)
                    zout.write(file_path, arcname=out_file)
            
            print(f"Output ZIP ready: {output_zip_path}")
            
            # Determine download filename
            if filename.lower().endswith(".zip"):
                download_name = filename.replace(".zip", "_nobg.zip")
            else:
                download_name = "images_nobg.zip"
            
            # Return ZIP file
            response = send_file(
                output_zip_path,
                as_attachment=True,
                download_name=download_name,
                mimetype="application/zip"
            )
            
        # Single file processed, return in original format
        else:
            out_file = processed_files[0]
            out_path = os.path.join(output_dir, out_file)
            print(f"Returning single file: {out_file}")
            
            # Determine MIME type based on extension
            ext = Path(out_file).suffix.lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.webp': 'image/webp',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp',
                '.tiff': 'image/tiff',
                '.tif': 'image/tiff'
            }
            mime_type = mime_types.get(ext, 'image/png')
            
            # Return file in original format
            response = send_file(
                out_path,
                as_attachment=True,
                download_name=out_file,
                mimetype=mime_type
            )
        
        # Cleanup after response is closed
        def cleanup():
            try:
                print(f"Cleaning temp: {temp_root}")
                shutil.rmtree(temp_root)
            except Exception as e:
                print(f"Cleanup failed: {e}")
        
        response.call_on_close(cleanup)
        return response

    except Exception as e:
        print("\n❌ GLOBAL ERROR:", e)
        traceback.print_exc()
        
        # Ensure cleanup on unexpected error
        try:
            if temp_root and os.path.exists(temp_root):
                shutil.rmtree(temp_root)
        except Exception:
            pass
        
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
