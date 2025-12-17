# app.py
import os
import io
import zipfile
import tempfile
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

import pikepdf

app = Flask(__name__)
CORS(app)

app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB upload limit
ALLOWED_EXTENSIONS = {'.pdf', '.zip'}

def allowed_filename(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in ALLOWED_EXTENSIONS)

class PasswordRequiredError(Exception):
    """Raised when a PDF requires a (correct) password which wasn't provided."""
    pass

def is_password_error(exc: Exception) -> bool:
    """
    Robust detection of a pikepdf password error:
    - If pikepdf exposes PasswordError class, use isinstance.
    - Otherwise, do a textual check of the exception message for typical phrases.
    """
    # Prefer explicit pikepdf.PasswordError if available
    pw_exc_cls = getattr(pikepdf, 'PasswordError', None)
    if pw_exc_cls and isinstance(exc, pw_exc_cls):
        return True
    # Some pikepdf versions raise internal types: fallback to message-inspection
    msg = str(exc).lower()
    if 'password' in msg or 'invalid password' in msg or 'incorrect password' in msg:
        return True
    return False

def process_pdf_file(path_on_disk, password):
    """
    Try to open the PDF with pikepdf. If it requires a password and the provided
    password is missing/incorrect, raise PasswordRequiredError.
    Return bytes of unlocked PDF on success.
    """
    try:
        with pikepdf.Pdf.open(path_on_disk, password=password) as pdf:
            out_buf = io.BytesIO()
            pdf.save(out_buf)
            out_buf.seek(0)
            return out_buf.read()
    except Exception as e:
        if is_password_error(e):
            # clearly indicate password-related problem
            raise PasswordRequiredError(str(e))
        # propagate other exceptions
        raise

@app.route('/', methods=['GET'])
def home():
    return "PDF Unlock service. POST /unlock-pdf with 'file' and optional 'password'."

@app.route('/unlock-pdf', methods=['POST'])
def unlock_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    upload = request.files['file']
    password = request.form.get('password', '') or None

    if upload.filename == '':
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(upload.filename)
    if not allowed_filename(filename):
        return jsonify({"error": f"Unsupported file type: {filename}"}), 400

    with tempfile.TemporaryDirectory() as workdir:
        uploaded_path = os.path.join(workdir, filename)
        upload.save(uploaded_path)

        unlocked_files = []

        if filename.lower().endswith('.pdf'):
            try:
                out_bytes = process_pdf_file(uploaded_path, password)
            except PasswordRequiredError:
                # return a JSON 401 so the frontend can show "incorrect password"
                return jsonify({"error": "Password required or incorrect for this PDF."}), 401
            except Exception as e:
                # Unexpected error; return 500 with json message (not a stack dump)
                return jsonify({"error": f"Server error: {str(e)}"}), 500

            return send_file(
                io.BytesIO(out_bytes),
                as_attachment=True,
                download_name=(os.path.splitext(filename)[0] + '_unlocked.pdf'),
                mimetype='application/pdf'
            )

        elif filename.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(uploaded_path, 'r') as z:
                    namelist = z.namelist()
                    for member in namelist:
                        if member.endswith('/'):
                            continue
                        if not member.lower().endswith('.pdf'):
                            continue
                        member_secure = os.path.basename(member)
                        extracted_path = os.path.join(workdir, member_secure)
                        with z.open(member) as src, open(extracted_path, 'wb') as dst:
                            dst.write(src.read())
                        try:
                            out_bytes = process_pdf_file(extracted_path, password)
                            out_name = os.path.splitext(member_secure)[0] + '_unlocked.pdf'
                            unlocked_files.append((out_name, out_bytes))
                        except PasswordRequiredError:
                            return jsonify({"error": f"Password required or incorrect for file inside zip: {member}"}), 401

                if len(unlocked_files) == 0:
                    return jsonify({"error": "No PDF files found inside the zip."}), 400

                out_zip_buf = io.BytesIO()
                with zipfile.ZipFile(out_zip_buf, 'w', zipfile.ZIP_DEFLATED) as out_zip:
                    for out_name, out_bytes in unlocked_files:
                        out_zip.writestr(out_name, out_bytes)
                out_zip_buf.seek(0)
                return send_file(
                    out_zip_buf,
                    as_attachment=True,
                    download_name=(os.path.splitext(filename)[0] + '_unlocked.zip'),
                    mimetype='application/zip'
                )

            except zipfile.BadZipFile:
                return jsonify({"error": "Uploaded file is not a valid zip."}), 400
            except Exception as e:
                return jsonify({"error": f"Server error: {str(e)}"}), 500
        else:
            return jsonify({"error": "Unsupported file type"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
