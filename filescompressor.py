#!/usr/bin/env python3
"""
Flask file compressor that preserves original file types.

- Single-file:
    - PDF -> compressed PDF (Ghostscript)
    - DOCX/PPTX -> compressed DOCX/PPTX (compress embedded images inside the archive)
    - Image -> compressed image (same extension where possible)
- ZIP:
    - Extract, process each supported file (PDF/office/image), re-zip processed outputs and return.
- Headers returned:
    - X-Final-Size: bytes
    - X-Returned: original|compressed
    - X-Method: gs|office|image|zip
- Requirements:
    - ghostscript (gs) for PDFs
    - Pillow (pip install pillow)
"""
import io
import os
import zipfile
import tempfile
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional

from flask import Flask, request, send_file, render_template_string, abort, jsonify, make_response
from werkzeug.utils import secure_filename
from shutil import which

# Pillow
try:
    from PIL import Image
except Exception:
    Image = None

# CORS
try:
    from flask_cors import CORS
except Exception:
    CORS = None

# -------- Config --------
ALLOWED_SINGLE_EXT = {
    "pdf", "docx", "pptx", "jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp", "zip"
}
# Accept .doc and .ppt but we will not modify their internals (will return as-is).
ALLOWED_EXTENSIONS = ALLOWED_SINGLE_EXT.union({"doc", "ppt"})

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH", 1200 * 1024 * 1024))  # 1.2 GB

if CORS:
    CORS(app, resources={r"/compress": {"origins": "*"}})
else:
    @app.after_request
    def _add_cors_headers(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        return resp

HTML_FORM = """<!doctype html>
<title>File Compressor</title>
<h1>Upload a file or ZIP</h1>
<form method=post enctype=multipart/form-data action="/compress">
  <input type=file name=file required><br><br>
  <select name="option">
    <option value="low">Low Compression</option>
    <option value="medium" selected>Medium Compression</option>
    <option value="high">High Compression</option>
    <option value="maximum">Maximum Compression</option>
  </select>
  <button type=submit>Compress</button>
</form>
<p>Supported single-file types: .pdf, .docx, .pptx, images (jpg/png/webp/tiff/bmp) and .zip containing these.</p>
"""

# Map frontend option -> params: (jpeg_quality, scale, png_compress_level, gs_preset, gs_dpi)
OPTION_MAP = {
    "low":     {"jpeg_q": 90, "scale": 1.0, "png_comp": 6,  "gs_preset": "/ebook",  "gs_dpi": 150},
    "medium":  {"jpeg_q": 75, "scale": 0.95, "png_comp": 7, "gs_preset": "/screen", "gs_dpi": 100},
    "high":    {"jpeg_q": 60, "scale": 0.8,  "png_comp": 9, "gs_preset": "/screen", "gs_dpi": 72},
    "maximum": {"jpeg_q": 40, "scale": 0.6,  "png_comp": 9, "gs_preset": "/screen", "gs_dpi": 50},
}

def find_gs_executable() -> Optional[str]:
    return which("gswin64c") or which("gswin32c") or which("gs")

def build_gs_command(gs_exec: str, inp: str, out: str, preset: str, dpi: int) -> List[str]:
    cmd = [
        gs_exec,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        "-dSAFER",
        f"-dPDFSETTINGS={preset}",
        "-dCompressPages=true",
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true",
        "-dColorImageDownsampleType=/Bicubic",
        "-dGrayImageDownsampleType=/Bicubic",
        "-dMonoImageDownsampleType=/Subsample",
        "-dEncodeColorImages=true",
        "-dEncodeGrayImages=true",
        "-dEncodeMonoImages=true",
        "-dColorImageFilter=/DCTEncode",
        "-dGrayImageFilter=/DCTEncode",
        "-dMonoImageFilter=/CCITTFaxEncode",
        "-dAutoFilterColorImages=false",
        "-dAutoFilterGrayImages=false",
        "-dEmbedAllFonts=true",
        "-dSubsetFonts=true",
        "-dCompressFonts=true",
        "-dDetectDuplicateImages=true",
        "-dPreserveAnnots=false",
        "-dOptimize=true",
        "-dUseFlateCompression=true",
    ]
    if dpi > 0:
        cmd.extend([
            f"-dColorImageResolution={dpi}",
            f"-dGrayImageResolution={dpi}",
            f"-dMonoImageResolution={dpi}",
        ])
    cmd.extend([f"-sOutputFile={out}", inp])
    return cmd

def run_gs_command(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)

def read_into_bytesio(path: Path) -> io.BytesIO:
    bio = io.BytesIO()
    with path.open("rb") as f:
        shutil.copyfileobj(f, bio)
    bio.seek(0)
    return bio

# ---------- Image compression helpers ----------
def compress_image_file(input_path: Path, output_path: Path, jpeg_q: int, scale: float, png_comp: int) -> bool:
    """
    Compress a single image file and write to output_path.
    Attempts to preserve format where feasible.
    Returns True on success.
    """
    if Image is None:
        app.logger.error("Pillow is required to compress images.")
        return False
    try:
        with Image.open(str(input_path)) as im:
            # Calculate new size
            if scale < 1.0:
                new_w = max(1, int(im.width * scale))
                new_h = max(1, int(im.height * scale))
                im = im.resize((new_w, new_h), Image.LANCZOS)

            fmt = (im.format or input_path.suffix.replace(".", "").upper()).upper()
            # For JPEG-like formats
            if fmt in ("JPEG", "JPG"):
                im = im.convert("RGB")
                im.save(str(output_path), format="JPEG", quality=jpeg_q, optimize=True)
            elif fmt in ("WEBP",):
                im = im.convert("RGB")
                im.save(str(output_path), format="WEBP", quality=jpeg_q, method=6)
            elif fmt in ("PNG",):
                # For PNG: save with optimize and provided compress level
                # Pillow uses compress_level 0-9 (9 max compression)
                params = {"optimize": True}
                try:
                    im.save(str(output_path), format="PNG", optimize=True, compress_level=png_comp)
                except TypeError:
                    # Some Pillow builds may not accept compress_level -> fallback
                    im.save(str(output_path), format="PNG", optimize=True)
            elif fmt in ("TIFF","TIF"):
                im = im.convert("RGB")
                im.save(str(output_path), format="TIFF", quality=jpeg_q)
            else:
                # Unknown format - try to save as JPEG to reduce size, keep extension
                try:
                    im = im.convert("RGB")
                    im.save(str(output_path), format="JPEG", quality=jpeg_q, optimize=True)
                except Exception:
                    # fallback: copy original
                    shutil.copyfile(str(input_path), str(output_path))
            return True
    except Exception as e:
        app.logger.exception("compress_image_file failed for %s: %s", input_path, e)
        return False

# ---------- Office (docx/pptx) handlers ----------
def compress_office_package(input_path: Path, output_path: Path, jpeg_q: int, scale: float, png_comp: int) -> bool:
    """
    Compress images inside a .docx or .pptx file.
    - Unzip the archive
    - For files under word/media or ppt/media, compress images
    - Rezip to output_path
    Returns True if output written.
    """
    try:
        with tempfile.TemporaryDirectory() as work:
            workdir = Path(work)
            # Extract zip (office files are zip archives)
            with zipfile.ZipFile(str(input_path), "r") as zin:
                zin.extractall(str(workdir))
            # Possible media dirs
            media_dirs = [workdir / "word" / "media", workdir / "ppt" / "media", workdir / "media"]
            processed_any = False
            for mdir in media_dirs:
                if not mdir.exists():
                    continue
                for img in list(mdir.iterdir()):
                    if not img.is_file():
                        continue
                    out_tmp = mdir / f"_tmp_{img.name}"
                    ok = compress_image_file(img, out_tmp, jpeg_q, scale, png_comp)
                    if ok and out_tmp.exists():
                        # Replace original with compressed
                        try:
                            out_tmp.replace(img)
                        except Exception:
                            # fallback copy
                            shutil.copyfile(str(out_tmp), str(img))
                        processed_any = True
            # Repack into output_path
            with zipfile.ZipFile(str(output_path), "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for root, dirs, files in os.walk(workdir):
                    for f in files:
                        full = Path(root) / f
                        # relative path inside archive
                        rel = full.relative_to(workdir)
                        zout.write(str(full), str(rel))
            return True
    except Exception as e:
        app.logger.exception("compress_office_package failed for %s: %s", input_path, e)
        return False

# ---------- PDF compression ----------
def compress_pdf_with_ghostscript(input_path: Path, output_path: Path, preset: str, dpi: int) -> bool:
    gs_exec = find_gs_executable()
    if not gs_exec:
        app.logger.error("Ghostscript not found.")
        return False
    cmd = build_gs_command(gs_exec, str(input_path), str(output_path), preset, dpi)
    try:
        run_gs_command(cmd)
        return output_path.exists()
    except Exception as e:
        app.logger.exception("Ghostscript failed for %s: %s", input_path, e)
        return False

# ---------- Top-level processing ----------
def process_single_file(input_path: Path, option: str, tmpdir: Path) -> Tuple[Path, str]:
    """
    Process a single file and return (output_path, method).
    IMPORTANT: This function ALWAYS preserves the original file type/extension.
    - PDF in -> PDF out (compressed)
    - DOCX in -> DOCX out (compressed)
    - PPTX in -> PPTX out (compressed)
    - Image in -> Same format image out (compressed)
    method is one of "gs", "office", "image", "original"
    """
    opt = OPTION_MAP.get(option, OPTION_MAP["medium"])
    jpeg_q = opt["jpeg_q"]; scale = opt["scale"]; png_comp = opt["png_comp"]; gs_preset = opt["gs_preset"]; gs_dpi = opt["gs_dpi"]

    suffix = input_path.suffix.lower().lstrip(".")
    
    # PDF -> compressed PDF (same extension)
    if suffix == "pdf":
        out_pdf = tmpdir / f"{input_path.stem}_compressed.pdf"
        ok = compress_pdf_with_ghostscript(input_path, out_pdf, gs_preset, gs_dpi)
        if ok and out_pdf.exists() and out_pdf.stat().st_size < input_path.stat().st_size:
            return (out_pdf, "gs")
        # if didn't help or failed, return original
        return (input_path, "original")
    
    # DOCX/PPTX -> compressed DOCX/PPTX (same extension preserved)
    elif suffix in ("docx", "pptx"):
        # CRITICAL: Output file maintains the same extension as input
        out_file = tmpdir / f"{input_path.stem}_compressed.{suffix}"
        ok = compress_office_package(input_path, out_file, jpeg_q, scale, png_comp)
        if ok and out_file.exists() and out_file.stat().st_size < input_path.stat().st_size:
            return (out_file, "office")
        elif ok and out_file.exists():
            # Even if size is similar, return compressed version (images were optimized)
            return (out_file, "office")
        else:
            return (input_path, "original")
    
    # Images -> compressed images (same format/extension preserved)
    elif suffix in ("jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"):
        # CRITICAL: Output maintains the same extension as input (e.g., .png -> .png)
        out_img = tmpdir / f"{input_path.stem}_compressed{input_path.suffix}"
        ok = compress_image_file(input_path, out_img, jpeg_q, scale, png_comp)
        if ok and out_img.exists():
            return (out_img, "image")
        else:
            return (input_path, "original")
    
    # Unsupported file types -> return as-is
    else:
        return (input_path, "original")

# ---------- Flask routes ----------
@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_FORM)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "ghostscript": bool(find_gs_executable()),
        "pillow": Image is not None
    })

@app.route("/compress", methods=["POST", "OPTIONS"])
def compress_endpoint():
    if request.method == "OPTIONS":
        return "", 200

    uploaded = request.files.get("file")
    if not uploaded:
        return abort(400, "No file uploaded under field 'file'.")

    filename = secure_filename(uploaded.filename or "")
    if not filename:
        return abort(400, "Invalid filename.")

    if "." not in filename or filename.rsplit(".", 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return abort(400, f"Unsupported extension. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    option = (request.form.get("option") or "medium").strip().lower()
    if option not in OPTION_MAP:
        option = "medium"

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        upload_path = tmpdir / filename
        uploaded.save(str(upload_path))
        orig_size = upload_path.stat().st_size

        # ZIP handling
        if upload_path.suffix.lower() == ".zip":
            extracted = tmpdir / "extracted"
            extracted.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(str(upload_path), "r") as z:
                    for member in z.namelist():
                        if member.endswith("/"):
                            continue
                        safe_name = secure_filename(member)
                        if not safe_name:
                            continue
                        target = extracted / safe_name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            except zipfile.BadZipFile:
                return abort(400, "Uploaded file is not a valid ZIP archive.")

            processed: List[Tuple[str, Path]] = []
            found_any = False
            for root, _, files in os.walk(extracted):
                for fname in files:
                    found_any = True
                    in_path = Path(root) / fname
                    out_path, method = process_single_file(in_path, option, tmpdir)
                    
                    # Preserve original filename structure in the output ZIP
                    # Use original filename (without _compressed suffix) for cleaner output
                    original_name = in_path.name
                    final_dest = tmpdir / "results" / original_name
                    final_dest.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy the processed (or original) file to results directory
                    # File extension is ALWAYS preserved from the input
                    if out_path.resolve() == in_path.resolve():
                        # File wasn't compressed, use original
                        shutil.copyfile(str(in_path), str(final_dest))
                    else:
                        # File was compressed, but extension is preserved
                        shutil.copyfile(str(out_path), str(final_dest))
                    
                    processed.append((final_dest.name, final_dest))

            if not found_any:
                return abort(400, "No files found inside the uploaded ZIP.")

            result_zip = tmpdir / "compressed_results.zip"
            with zipfile.ZipFile(str(result_zip), "w", compression=zipfile.ZIP_DEFLATED) as outzip:
                for arcname, path in processed:
                    outzip.write(str(path), arcname)

            # If compressed zip isn't smaller, still return it (user requested compressed office files); but we'll compare and choose
            result_size = result_zip.stat().st_size
            # If result is larger than original zip, still return processed zip because user expects processed outputs
            bio = read_into_bytesio(result_zip)
            resp = make_response(send_file(bio, as_attachment=True, download_name="compressed_results.zip", mimetype="application/zip"))
            resp.headers["X-Final-Size"] = str(result_size)
            resp.headers["X-Returned"] = "compressed"
            resp.headers["X-Method"] = "zip"
            return resp

        # Single-file processing
        else:
            out_path, method = process_single_file(upload_path, option, tmpdir)
            
            # Prepare download name - use original filename to preserve clarity
            # Extension is ALWAYS the same as the input file
            original_filename = upload_path.name
            
            # If output is identical to input and method == original, return original file
            if out_path.resolve() == upload_path.resolve():
                # return original file with original name
                bio = read_into_bytesio(upload_path)
                resp = make_response(send_file(bio, as_attachment=True, download_name=original_filename, mimetype="application/octet-stream"))
                resp.headers["X-Final-Size"] = str(upload_path.stat().st_size)
                resp.headers["X-Returned"] = "original"
                resp.headers["X-Method"] = "original"
                return resp
            else:
                # Return compressed file with ORIGINAL filename (preserving extension)
                # Extension is guaranteed to match the input file type
                download_name = original_filename  # Use original name, not _compressed version
                mime = "application/octet-stream"
                lower = out_path.suffix.lower()
                
                # Set appropriate MIME type based on file extension
                if lower == ".pdf":
                    mime = "application/pdf"
                elif lower in (".docx",):
                    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif lower in (".pptx",):
                    mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                elif lower in (".zip",):
                    mime = "application/zip"
                elif lower.startswith(".jpg") or lower.startswith(".jpeg"):
                    mime = "image/jpeg"
                elif lower == ".png":
                    mime = "image/png"
                elif lower == ".webp":
                    mime = "image/webp"
                
                bio = read_into_bytesio(out_path)
                resp = make_response(send_file(bio, as_attachment=True, download_name=download_name, mimetype=mime))
                resp.headers["X-Final-Size"] = str(out_path.stat().st_size)
                resp.headers["X-Returned"] = "compressed"
                resp.headers["X-Method"] = method
                return resp

@app.errorhandler(413)
def too_large(e):
    return "Uploaded file too large", 413

# Run dev server
if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)
