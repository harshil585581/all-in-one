# upscale_server.py
import os
import zipfile
import traceback
import tempfile
import shutil
import uuid
import gc
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from PIL import Image, ImageFile

# Allow partial and large images
ImageFile.LOAD_TRUNCATED_IMAGES = True

app = Flask(__name__)

CORS(app, resources={r"/*": {
    "origins": "*",
    "allow_headers": "*",
    "expose_headers": "*",
    "methods": ["GET", "POST", "OPTIONS"],
}}, supports_credentials=False)

app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

# Default allowed image extensions
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}

# Allowed upscale levels
ALLOWED_SCALES = {2, 4, 8, 16}


def is_image_filename(name: str) -> bool:
    _, ext = os.path.splitext(name.lower())
    return ext in ALLOWED_EXT


@app.get("/")
def index():
    return jsonify({"status": "ok", "note": "Upscale API running"})


@app.post("/upscale")
def upscale_zip_or_image():
    print("---- /upscale HIT ----")
    temp_root = None
    try:
        # Check file presence
        if "file" not in request.files:
            print("❌ ERROR: No file found in request")
            return jsonify({"error": "No file uploaded"}), 400

        uploaded = request.files["file"]
        filename = uploaded.filename or "uploaded"
        print("Uploaded filename:", filename, "mimetype:", uploaded.mimetype)

        # Read scale from form (default 2)
        raw_scale = request.form.get("scale", "2")
        try:
            scale = int(raw_scale)
            if scale not in ALLOWED_SCALES:
                raise ValueError("Invalid scale")
        except Exception as e:
            print("❌ SCALE ERROR:", raw_scale, e)
            return jsonify({"error": "Invalid scale. Allowed values: 2,4,8,16"}), 400

        print("Requested scale:", scale)

        # Temp directory
        temp_root = tempfile.mkdtemp(prefix="upscale_")
        print("Temp directory:", temp_root)

        input_dir = os.path.join(temp_root, "input")
        output_dir = os.path.join(temp_root, "output")
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        # Save uploaded file to disk
        uploaded_path = os.path.join(temp_root, filename)
        uploaded.save(uploaded_path)
        print("Saved uploaded file at:", uploaded_path)

        processed_any = False

        # If uploaded file is a zip (by extension or mimetype), try to extract
        if filename.lower().endswith(".zip") or uploaded.mimetype == "application/zip":
            try:
                with zipfile.ZipFile(uploaded_path, "r") as ztest:
                    test = ztest.testzip()
                    if test is not None:
                        print("❌ zip.testzip flagged bad member:", test)
                        return jsonify({"error": "ZIP file appears corrupted"}), 400
            except zipfile.BadZipFile as bz:
                print("❌ BadZipFile:", bz)
                return jsonify({"error": "Uploaded file is not a valid ZIP file"}), 400
            except Exception as e:
                print("❌ ZIP VALIDATION ERROR:", e)
                return jsonify({"error": "Could not validate ZIP file"}), 400

            # Extract
            try:
                with zipfile.ZipFile(uploaded_path, "r") as z:
                    print("ZIP entries:", z.namelist())
                    z.extractall(input_dir)
            except Exception as e:
                print("❌ ZIP EXTRACT ERROR:", e)
                raise

            # Process extracted files (top-level and nested)
            for root, dirs, files in os.walk(input_dir):
                for fname in files:
                    rel = os.path.relpath(os.path.join(root, fname), input_dir)
                    if not is_image_filename(fname):
                        print("Skipping non-image:", rel)
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with Image.open(fpath) as img:
                            print("Opened image:", rel, "size:", img.size)
                            img = img.convert("RGB")
                            new_size = (img.width * scale, img.height * scale)
                            upscaled = img.resize(new_size, Image.LANCZOS)

                            out_name = f"upscaled_{os.path.splitext(fname)[0]}_{uuid.uuid4().hex}.jpg"
                            out_path = os.path.join(output_dir, out_name)
                            upscaled.save(out_path, "JPEG", quality=90)
                            print("Saved:", out_path)
                            processed_any = True
                            del upscaled
                    except Exception as e:
                        print("❌ IMAGE PROCESS ERROR for", rel, ":", e)
                        traceback.print_exc()
                    finally:
                        gc.collect()

        # Else if uploaded file is an image -> process single image
        elif uploaded.mimetype and uploaded.mimetype.startswith("image") or is_image_filename(filename):
            # Save the image into input_dir
            input_image_path = os.path.join(input_dir, filename)
            shutil.move(uploaded_path, input_image_path)
            print("Saved single image at:", input_image_path)

            try:
                with Image.open(input_image_path) as img:
                    print("Opened image:", filename, "size:", img.size)
                    img = img.convert("RGB")
                    new_size = (img.width * scale, img.height * scale)
                    upscaled = img.resize(new_size, Image.LANCZOS)

                    out_name = f"upscaled_{os.path.splitext(filename)[0]}_{uuid.uuid4().hex}.jpg"
                    out_path = os.path.join(output_dir, out_name)
                    upscaled.save(out_path, "JPEG", quality=90)
                    print("Saved:", out_path)
                    processed_any = True
                    del upscaled
            except Exception as e:
                print("❌ IMAGE PROCESS ERROR for", filename, ":", e)
                traceback.print_exc()
            finally:
                gc.collect()

        else:
            print("❌ Unsupported uploaded file type:", filename, uploaded.mimetype)
            return jsonify({"error": "Uploaded file must be a ZIP containing images or a single image file."}), 400

        if not processed_any:
            return jsonify({"error": "No valid image files were processed. Allowed: jpg, png, webp, bmp, tiff"}), 400

        # Create output ZIP
        output_zip_path = os.path.join(temp_root, f"upscaled_x{scale}.zip")
        with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for out_file in sorted(os.listdir(output_dir)):
                zout.write(os.path.join(output_dir, out_file), arcname=out_file)

        print("Output ZIP ready:", output_zip_path)

        # Return file as attachment. send_file sets content-disposition header.
        response = send_file(output_zip_path, as_attachment=True)
        # cleanup after response is closed
        def cleanup():
            try:
                print("Cleaning temp:", temp_root)
                shutil.rmtree(temp_root)
            except Exception as e:
                print("Cleanup failed:", e)
        response.call_on_close(cleanup)
        return response

    except Exception as e:
        print("\n❌ GLOBAL ERROR:", e)
        traceback.print_exc()
        # ensure cleanup on unexpected error
        try:
            if temp_root and os.path.exists(temp_root):
                shutil.rmtree(temp_root)
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
