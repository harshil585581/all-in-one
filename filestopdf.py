#!/usr/bin/env python3
"""
Windows-friendly Flask app (API-only) to convert files -> PDF.

Endpoints:
 - GET  /status    -> JSON status (soffice/wkhtmltopdf/docx2pdf/pywin32 availability)
 - POST /file-pdf  -> form field "file" (single file or a .zip). Returns PDF or ZIP of PDFs.

Improved DOC/DOCX handling:
 - Try docx2pdf (Python package)
 - Then try Word COM (pywin32 / win32com)
 - Then fallback to LibreOffice (`soffice`)

Usage (recommended on Windows):
 pip install flask pillow flask-cors docx2pdf pywin32
 Install Microsoft Word OR LibreOffice (soffice) for fallbacks.
"""
import os
import zipfile
import tempfile
import shutil
import subprocess
import platform
from pathlib import Path
from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
from flask_cors import CORS

# docx2pdf and win32com are optional; import if available
DOCX2PDF_AVAILABLE = False
try:
    from docx2pdf import convert as docx2pdf_convert  # type: ignore
    DOCX2PDF_AVAILABLE = True
except Exception:
    DOCX2PDF_AVAILABLE = False

WIN32COM_AVAILABLE = False
try:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore
    WIN32COM_AVAILABLE = True
except Exception:
    WIN32COM_AVAILABLE = False

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB - adjust if needed

ALLOWED_EXTS = {
    '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
    '.html',
    '.jpg', '.jpeg', '.png', '.webp',
    '.txt', '.pdf'
}


# ---------------- utilities ----------------

def which_binary(name: str):
    from shutil import which
    return which(name)


def run_subprocess(cmd):
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        stdout = proc.stdout.decode(errors='replace') if proc.stdout else ''
        stderr = proc.stderr.decode(errors='replace') if proc.stderr else ''
        return proc.returncode, stdout, stderr
    except FileNotFoundError:
        return None, '', f'binary not found: {cmd[0]}'
    except Exception as e:
        return -1, '', f'exception: {e}'


# ---------------- converters ----------------

def run_soffice_convert_to_pdf(src: Path, outdir: Path):
    soffice = which_binary("soffice") or which_binary("soffice.exe")
    if not soffice:
        return None, "soffice not found in PATH"
    cmd = [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(outdir), str(src)]
    rc, out, err = run_subprocess(cmd)
    expected = outdir / (src.stem + ".pdf")
    if expected.exists():
        return expected, f"soffice ok (rc={rc})"
    return None, f"soffice failed (rc={rc}) stdout={out[:400]} stderr={err[:400]}"


def try_docx2pdf_windows(src: Path, out_pdf: Path):
    if not DOCX2PDF_AVAILABLE:
        return None, "docx2pdf package not available"
    # docx2pdf will write into out dir
    try:
        out_dir = out_pdf.parent
        # docx2pdf.convert accepts (input_path, output_path_dir)
        docx2pdf_convert(str(src), str(out_dir))
        produced = out_dir / (src.stem + ".pdf")
        if produced.exists():
            if produced.resolve() != out_pdf.resolve():
                shutil.move(str(produced), str(out_pdf))
            return out_pdf, "docx2pdf OK"
        return None, "docx2pdf converted but output file not found"
    except Exception as e:
        return None, f"docx2pdf exception: {e}"


def try_win32com_word_to_pdf(src: Path, out_pdf: Path, timeout_seconds: int = 30):
    """
    Use Word COM automation (win32com) to convert DOC/DOCX -> PDF.
    This requires pywin32 and MS Word installed.
    """
    if not WIN32COM_AVAILABLE:
        return None, "win32com (pywin32) not available"
    try:
        # initialize COM in this thread
        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        # Open the document (ReadOnly True)
        doc = None
        try:
            doc = word.Documents.Open(str(src), ReadOnly=1, Visible=False)
            # wdFormatPDF = 17
            doc.ExportAsFixedFormat(str(out_pdf), 17)  # ExportAsFixedFormat(outputFileName, ExportFormat=17)
            # sometimes doc.Close() is needed
            doc.Close(False)
            word.Quit()
        except Exception as e_inner:
            # attempt safe close
            try:
                if doc is not None:
                    doc.Close(False)
            except Exception:
                pass
            try:
                word.Quit()
            except Exception:
                pass
            return None, f"win32com conversion error: {e_inner}"
        finally:
            pythoncom.CoUninitialize()
        if out_pdf.exists():
            return out_pdf, "win32com Word export OK"
        return None, "win32com wrote no output file"
    except Exception as e:
        return None, f"win32com exception: {e}"


def html_to_pdf_wkhtmltopdf(src: Path, out_pdf: Path):
    wk = which_binary("wkhtmltopdf") or which_binary("wkhtmltopdf.exe")
    if not wk:
        return None, "wkhtmltopdf not found"
    cmd = [wk, str(src), str(out_pdf)]
    rc, out, err = run_subprocess(cmd)
    if out_pdf.exists():
        return out_pdf, f"wkhtmltopdf ok (rc={rc})"
    return None, f"wkhtmltopdf failed (rc={rc}) stdout={out[:400]} stderr={err[:400]}"


def image_to_pdf(src: Path, out_pdf: Path):
    try:
        with Image.open(src) as im:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                bg.save(out_pdf, "PDF", resolution=100.0)
            else:
                im.convert("RGB").save(out_pdf, "PDF", resolution=100.0)
        return out_pdf, "Pillow OK"
    except Exception as e:
        return None, f"Pillow error: {e}"


def convert_one_to_pdf(src: Path, working_dir: Path):
    """
    Convert one source file to PDF, returns (Path or None, details string).
    Improved DOCX path: docx2pdf -> pywin32 -> soffice
    """
    suffix = src.suffix.lower()
    out_pdf = working_dir / (src.stem + ".pdf")

    if suffix in (".jpg", ".jpeg", ".png", ".webp"):
        return image_to_pdf(src, out_pdf)

    if suffix in (".html", ".htm"):
        res, d = html_to_pdf_wkhtmltopdf(src, out_pdf)
        if res:
            return res, d
        res2, d2 = run_soffice_convert_to_pdf(src, working_dir)
        if res2:
            return res2, d2
        return None, f"HTML conversion failed: wkhtmltopdf: {d}; soffice: {d2}"

    if suffix in (".doc", ".docx"):
        # 1) docx2pdf python package (uses Word on Windows)
        if DOCX2PDF_AVAILABLE:
            res, d = try_docx2pdf_windows(src, out_pdf)
            if res:
                return res, f"docx2pdf: {d}"
            # if it failed, continue to next fallback and include details
            last_docx_err = d
        else:
            last_docx_err = "docx2pdf not installed"

        # 2) pywin32 COM (win32com) fallback on Windows
        if platform.system().lower() == "windows" and WIN32COM_AVAILABLE:
            res, d2 = try_win32com_word_to_pdf(src, out_pdf)
            if res:
                return res, f"win32com: {d2}"
            last_docx_err = f"{last_docx_err}; win32com: {d2}"
        elif platform.system().lower() == "windows":
            last_docx_err = f"{last_docx_err}; win32com not available"

        # 3) soffice fallback (LibreOffice)
        res3, d3 = run_soffice_convert_to_pdf(src, working_dir)
        if res3:
            return res3, f"soffice fallback: {d3}; previous: {last_docx_err}"
        return None, f"docx conversion failed: {last_docx_err}; soffice: {d3}"

    if suffix in (".ppt", ".pptx", ".xls", ".xlsx", ".txt"):
        res, d = run_soffice_convert_to_pdf(src, working_dir)
        if res:
            return res, d
        return None, f"soffice conversion failed: {d}"

    if suffix == ".pdf":
        dst = working_dir / src.name
        shutil.copy(str(src), str(dst))
        return dst, "pdf passthrough (copied)"

    return None, f"unsupported suffix: {suffix}"


# ---------------- endpoints ----------------

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "platform": platform.system(),
        "docx2pdf_available": DOCX2PDF_AVAILABLE,
        "win32com_available": WIN32COM_AVAILABLE,
        "soffice": which_binary("soffice") or which_binary("soffice.exe") or "not-found",
        "wkhtmltopdf": which_binary("wkhtmltopdf") or which_binary("wkhtmltopdf.exe") or "not-found",
    })


@app.route("/file-pdf", methods=["POST"])
def file_pdf():
    if "file" not in request.files:
        return jsonify({"error": "no file part"}), 400
    uploaded = request.files["file"]
    if uploaded.filename == "":
        return jsonify({"error": "no selected file"}), 400

    filename = secure_filename(uploaded.filename)
    suffix = Path(filename).suffix.lower()
    if not (suffix in ALLOWED_EXTS or filename.lower().endswith(".zip")):
        return jsonify({"error": f"unsupported file type: {filename}"}), 400

    tmp_root = Path(tempfile.mkdtemp(prefix="conv_"))
    try:
        upload_path = tmp_root / filename
        uploaded.save(str(upload_path))

        # ZIP handling: extract and convert all supported files
        if filename.lower().endswith(".zip"):
            extracted = tmp_root / "extracted"
            extracted.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(upload_path, "r") as zin:
                    zin.extractall(path=str(extracted))
            except zipfile.BadZipFile:
                return jsonify({"error": "invalid zip archive"}), 400

            outdir = tmp_root / "outputs"
            outdir.mkdir(parents=True, exist_ok=True)
            outputs = []
            details_map = {}

            for root, _, files in os.walk(extracted):
                for name in files:
                    src = Path(root) / name
                    ext = Path(name).suffix.lower()
                    if ext not in ALLOWED_EXTS:
                        details_map[str(src.relative_to(extracted))] = "skipped-unsupported"
                        continue
                    res, det = convert_one_to_pdf(src, outdir)
                    details_map[str(src.relative_to(extracted))] = det
                    if res and res.exists():
                        outputs.append(res)

            if not outputs:
                return jsonify({"error": "no convertible files in zip", "details": details_map}), 400

            # if single output -> return pdf directly
            if len(outputs) == 1:
                p = outputs[0]
                return send_file(str(p), as_attachment=True, download_name=p.name, mimetype="application/pdf")

            # else pack into zip
            outzip = tmp_root / "converted_pdfs.zip"
            with zipfile.ZipFile(outzip, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for p in outputs:
                    zout.write(p, arcname=p.name)
            # also return details in header? (we return zip directly as before)
            return send_file(str(outzip), as_attachment=True, download_name="converted_pdfs.zip", mimetype="application/zip")

        else:
            outdir = tmp_root / "outputs"
            outdir.mkdir(parents=True, exist_ok=True)
            res, det = convert_one_to_pdf(upload_path, outdir)
            if not res:
                return jsonify({"error": "conversion failed or unsupported file type", "details": det}), 500
            return send_file(str(res), as_attachment=True, download_name=res.name, mimetype="application/pdf")

    finally:
        # best-effort cleanup
        try:
            shutil.rmtree(tmp_root)
        except Exception:
            pass


if __name__ == "__main__":
    print("Starting file->pdf API on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
