# watermarkfiles.py
import os
import io
import zipfile
import tempfile
import uuid
import subprocess
import logging
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.errors import FileNotDecryptedError
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("watermarkfiles")

app = Flask(__name__)
CORS(app)

# Try to register a common TTF font; adjust the path if needed on Windows
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    DEFAULT_FONT_NAME = 'DejaVuSans'
except Exception:
    DEFAULT_FONT_NAME = 'Helvetica'


def convert_docx_to_pdf(docx_path, out_dir):
    """
    Convert .docx to .pdf using LibreOffice headless (soffice).
    Returns the path to the created PDF or None on failure.
    """
    try:
        os.makedirs(out_dir, exist_ok=True)
        # Use soffice (LibreOffice). Ensure 'soffice' is available in PATH.
        subprocess.check_call(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', out_dir, docx_path],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = os.path.basename(docx_path)
        pdf_name = os.path.splitext(base)[0] + '.pdf'
        out_pdf = os.path.join(out_dir, pdf_name)
        if os.path.exists(out_pdf):
            return out_pdf
        logger.error("LibreOffice conversion didn't produce expected output: %s", out_pdf)
        return None
    except Exception as e:
        logger.exception("Error converting DOCX to PDF: %s", e)
        return None


def create_text_watermark_pdf(page_width, page_height, text, font_size, bold, rotation_deg, opacity, position):
    """
    Create a one-page watermark PDF (in-memory BytesIO) with the given text.
    position: 'top-left', 'top-center', 'top-right', 'middle-left', 'middle-center', ...
    opacity: float 0..1 (opacity)
    """
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))

    # set font (reportlab fallback)
    font_name = DEFAULT_FONT_NAME if DEFAULT_FONT_NAME else 'Helvetica'
    try:
        c.setFont(font_name, font_size)
    except Exception:
        c.setFont('Helvetica', font_size)

    # attempt to set transparency if supported
    try:
        c.setFillAlpha(opacity)
    except Exception:
        # older reportlab: ignore, will simulate via color alpha not available
        pass

    text_width = c.stringWidth(text, font_name, font_size)
    margin = 40

    # horizontal position
    if 'left' in position:
        x = margin
    elif 'center' in position:
        x = (page_width - text_width) / 2
    else:  # right
        x = page_width - text_width - margin

    # vertical position
    if 'top' in position:
        y = page_height - margin - font_size
    elif 'middle' in position:
        y = (page_height - font_size) / 2
    else:  # lower
        y = margin

    c.saveState()
    # rotate around text center
    cx = x + text_width / 2
    cy = y + font_size / 2
    c.translate(cx, cy)
    c.rotate(rotation_deg)
    c.translate(-cx, -cy)

    c.drawString(x, y, text)
    c.restoreState()
    c.save()
    packet.seek(0)
    return packet


def merge_watermark_into_reader(reader: PdfReader, watermark_pdf_bytes: bytes):
    """
    Overlay watermark (single-page PDF in bytes) over each page of the given (possibly decrypted) PdfReader.
    Returns bytes of the resulting PDF.
    """
    try:
        watermark_reader = PdfReader(io.BytesIO(watermark_pdf_bytes))
        watermark_page = watermark_reader.pages[0]
    except Exception as e:
        logger.exception("Failed to read watermark PDF bytes: %s", e)
        raise

    writer = PdfWriter()

    for p in reader.pages:
        try:
            # merge_page overlays watermark_page on top of p
            p.merge_page(watermark_page)
        except Exception:
            # attempt again or skip merge; try merge_page once more to raise
            p.merge_page(watermark_page)
        writer.add_page(p)

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()


def process_single_file(src_path, wtype, text, font_size, bold, rotation, position, opacity, image_file, tempdir, password=''):
    """
    Process a single file (pdf or docx) and return path to watermarked PDF.
    Raises FileNotDecryptedError if encrypted and password incorrect.
    """
    name = os.path.basename(src_path)
    base = os.path.splitext(name)[0]
    out_pdf_path = os.path.join(tempdir, base + '_watermarked.pdf')

    ext = os.path.splitext(name)[1].lower()
    if ext == '.docx':
        pdf_path = convert_docx_to_pdf(src_path, tempdir)
        if not pdf_path:
            raise Exception("DOCX -> PDF conversion failed")
        src_pdf_path = pdf_path
    elif ext == '.pdf':
        src_pdf_path = src_path
    else:
        raise Exception("Unsupported file type: " + ext)

    with open(src_pdf_path, 'rb') as fh:
        src_bytes = fh.read()

    # Create PdfReader and handle decryption if required
    reader = PdfReader(io.BytesIO(src_bytes))
    if getattr(reader, "is_encrypted", False):
        logger.info("PDF appears encrypted: %s", src_pdf_path)
        # Try to decrypt using provided password (user password)
        try:
            # PyPDF2.decrypt returns truthy on success (older versions return int)
            success = False
            try:
                res = reader.decrypt(password or '')
                success = bool(res)
            except Exception:
                # Some PyPDF2 versions may raise; catch and try again
                success = False

            if not success:
                # Try empty password fallback
                try:
                    res2 = reader.decrypt('')
                    success = bool(res2)
                except Exception:
                    success = False

            if not success:
                logger.warning("Failed to decrypt %s with provided password.", src_pdf_path)
                raise FileNotDecryptedError("File has not been decrypted")
        except FileNotDecryptedError:
            raise
        except Exception as e:
            logger.exception("Error while attempting to decrypt: %s", e)
            raise FileNotDecryptedError("File has not been decrypted")

    # Now safe to access pages
    if len(reader.pages) == 0:
        raise Exception("PDF has no pages")

    page0 = reader.pages[0]
    try:
        w = float(page0.mediabox.width)
        h = float(page0.mediabox.height)
    except Exception:
        w, h = letter

    # Build watermark PDF bytes
    if wtype == 'text':
        wm_pdf_io = create_text_watermark_pdf(w, h, text, font_size, bold, rotation, opacity, position)
        wm_pdf_bytes = wm_pdf_io.read()
    else:
        # Image watermark path: need image_file (a FileStorage from request.files) passed from caller
        if not image_file:
            raise Exception("No watermark image provided for image watermark type")
        try:
            image_file.stream.seek(0)
            pil = Image.open(image_file.stream).convert("RGBA")
        except Exception as e:
            logger.exception("Invalid watermark image: %s", e)
            raise Exception("Invalid watermark image")

        # apply opacity by modulating alpha channel
        if opacity < 1.0:
            try:
                r, g, b, a = pil.split()
                new_alpha = a.point(lambda p: int(p * opacity))
                pil.putalpha(new_alpha)
            except Exception:
                pass

        if rotation != 0:
            pil = pil.rotate(rotation, expand=True)

        tmp_img = os.path.join(tempdir, str(uuid.uuid4()) + '.png')
        pil.save(tmp_img, format='PNG')

        # create watermark PDF embedding the image
        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=(w, h))
        try:
            c.setFillAlpha(opacity)
        except Exception:
            pass

        img_reader = ImageReader(tmp_img)
        iw, ih = img_reader.getSize()
        target_w = w * 0.4
        scale = target_w / iw if iw > 0 else 1.0
        draw_w = iw * scale
        draw_h = ih * scale
        margin = 40
        if 'left' in position:
            x = margin
        elif 'center' in position:
            x = (w - draw_w) / 2
        else:
            x = w - draw_w - margin

        if 'top' in position:
            y = h - draw_h - margin
        elif 'middle' in position:
            y = (h - draw_h) / 2
        else:
            y = margin

        c.saveState()
        cx = x + draw_w / 2
        cy = y + draw_h / 2
        c.translate(cx, cy)
        c.rotate(rotation)
        c.translate(-cx, -cy)
        c.drawImage(img_reader, x, y, width=draw_w, height=draw_h, mask='auto')
        c.restoreState()
        c.save()
        packet.seek(0)
        wm_pdf_bytes = packet.read()

    # Merge watermark over every page using the existing (possibly decrypted) reader
    out_bytes = merge_watermark_into_reader(reader, wm_pdf_bytes)

    with open(out_pdf_path, 'wb') as fh:
        fh.write(out_bytes)
    return out_pdf_path


@app.route('/watermark-files', methods=['POST'])
def watermark_files():
    """
    Expects multipart/form-data:
      - file: single .pdf or .docx or .zip (with .pdf/.docx inside)
      - type: 'text' or 'image'
      - text: watermark text (if type=text)
      - font_size: int
      - bold: 'true'/'false'
      - rotation: degrees
      - position: 'top-left' etc.
      - transparency: '75'|'50'|'25'|'20'   (we treat as opacity percent)
      - password: optional password for encrypted PDFs
      - image_file: file (if type=image)
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files['file']
    name = f.filename or 'upload'
    lower = name.lower()
    if not any(lower.endswith(e) for e in ('.pdf', '.docx', '.zip')):
        return jsonify({"error": "Unsupported file type"}), 400

    # read form fields safely
    wtype = request.form.get('type', 'text')
    text = request.form.get('text', '')[:500]
    try:
        font_size = int(request.form.get('font_size', 48))
    except Exception:
        font_size = 48
    bold = request.form.get('bold', 'false').lower() == 'true'
    try:
        rotation = float(request.form.get('rotation', 0))
    except Exception:
        rotation = 0.0
    position = request.form.get('position', 'middle-center')
    transparency_pct = request.form.get('transparency', '50')
    try:
        transparency_pct = int(transparency_pct)
    except Exception:
        transparency_pct = 50
    # interpret transparency value as opacity percent (so 50 => 0.5 opacity)
    opacity = max(0.0, min(1.0, transparency_pct / 100.0))

    password = request.form.get('password', '') or ''
    image_file = request.files.get('image_file', None)

    tempdir = tempfile.mkdtemp(prefix='wmk_')
    out_files = []

    try:
        # if uploaded a zip, iterate its members
        if lower.endswith('.zip'):
            zip_bytes = f.read()
            try:
                z = zipfile.ZipFile(io.BytesIO(zip_bytes))
            except Exception:
                return jsonify({"error": "Invalid ZIP file"}), 400

            for zi in z.infolist():
                if zi.is_dir():
                    continue
                filename = zi.filename
                ext = os.path.splitext(filename)[1].lower()
                if ext not in ('.pdf', '.docx'):
                    logger.info("Skipping unsupported file inside ZIP: %s", filename)
                    continue
                data = z.read(zi)
                src_path = os.path.join(tempdir, str(uuid.uuid4()) + ext)
                with open(src_path, 'wb') as fh:
                    fh.write(data)
                try:
                    processed_path = process_single_file(src_path, wtype, text, font_size, bold, rotation, position, opacity, image_file, tempdir, password)
                    if processed_path:
                        out_files.append(processed_path)
                except FileNotDecryptedError:
                    return jsonify({"error": f"File '{filename}' inside ZIP is encrypted and password is incorrect or not provided."}), 400
                except Exception as e:
                    logger.exception("Failed processing file in ZIP: %s", filename)
                    return jsonify({"error": f"Processing failed for '{filename}': {str(e)}"}), 500

        else:
            # single file uploaded
            src_path = os.path.join(tempdir, 'upload' + os.path.splitext(name)[1])
            f.save(src_path)
            try:
                processed_path = process_single_file(src_path, wtype, text, font_size, bold, rotation, position, opacity, image_file, tempdir, password)
                if processed_path:
                    out_files.append(processed_path)
            except FileNotDecryptedError:
                return jsonify({"error": "File is encrypted and password is incorrect or not provided."}), 400
            except Exception as e:
                logger.exception("Failed processing uploaded file")
                return jsonify({"error": "Processing failed: " + str(e)}), 500

        if len(out_files) == 0:
            return jsonify({"error": "No supported files processed."}), 400

        if len(out_files) == 1:
            return send_file(out_files[0], as_attachment=True, download_name=os.path.basename(out_files[0]))
        else:
            memzip = io.BytesIO()
            with zipfile.ZipFile(memzip, mode='w') as zf:
                for p in out_files:
                    zf.write(p, arcname=os.path.basename(p))
            memzip.seek(0)
            return send_file(memzip, mimetype='application/zip', as_attachment=True, download_name='watermarked_files.zip')

    finally:
        # Optionally cleanup temporary directory and files here if desired.
        # For debugging you may keep files; in production remove them.
        pass


if __name__ == '__main__':
    app.run(debug=True, port=5000)
