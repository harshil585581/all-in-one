import os
import io
import zipfile
import tempfile
from flask import Flask, request, send_file, jsonify, after_this_request
from flask_cors import CORS
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader, PdfWriter

app = Flask(__name__)
CORS(app)

ALLOWED_EXT = {'.pdf', '.zip'}

def is_allowed_filename(filename):
    ext = os.path.splitext(filename.lower())[1]
    return ext in ALLOWED_EXT

def encrypt_pdf_bytes(pdf_bytes: bytes, password: str) -> bytes:
    """Return encrypted PDF bytes from input PDF bytes using PyPDF2."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    # copy pages
    for p in reader.pages:
        writer.add_page(p)

    # apply encrypt: both user and owner passwords can be same
    writer.encrypt(user_pwd=password, owner_pwd=None, use_128bit=True)

    out_stream = io.BytesIO()
    writer.write(out_stream)
    out_stream.seek(0)
    return out_stream.read()

@app.route('/protect-pdf', methods=['POST', 'OPTIONS'])
def protect_pdf():
    """
    Accept 'file' (single file) and 'password' (string).
    If file is .pdf -> return encrypted pdf. If .zip -> return zip of encrypted pdfs.
    """
    # Handle OPTIONS preflight request
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    
    if 'file' not in request.files:
        return jsonify({'error': 'Missing file'}), 400
    password = request.form.get('password', '')
    if not password:
        return jsonify({'error': 'Password is required'}), 400

    file = request.files['file']
    filename = secure_filename(file.filename or 'uploaded')
    if not filename:
        return jsonify({'error': 'Invalid filename'}), 400

    ext = os.path.splitext(filename.lower())[1]
    if ext == '.pdf':
        try:
            input_bytes = file.read()
            encrypted = encrypt_pdf_bytes(input_bytes, password)

            @after_this_request
            def cleanup(response):
                return response

            out_name = filename
            if out_name.lower().endswith('.pdf'):
                base = out_name[:-4]
            else:
                base = out_name
            out_name = f"{base}_protected.pdf"

            return send_file(
                io.BytesIO(encrypted),
                mimetype='application/pdf',
                as_attachment=True,
                download_name=out_name
            )
        except Exception as e:
            return jsonify({'error': f'Failed to encrypt PDF: {str(e)}'}), 500

    elif ext == '.zip':
        # process zip: extract pdfs, encrypt each, pack into new zip
        try:
            in_memory = io.BytesIO(file.read())
            input_zip = zipfile.ZipFile(in_memory)
        except Exception as e:
            return jsonify({'error': f'Invalid zip file: {str(e)}'}), 400

        out_buffer = io.BytesIO()
        with zipfile.ZipFile(out_buffer, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
            pdf_found = False
            for zinfo in input_zip.infolist():
                name = zinfo.filename
                # skip directories
                if name.endswith('/'):
                    continue
                lower = name.lower()
                if lower.endswith('.pdf'):
                    pdf_found = True
                    try:
                        raw = input_zip.read(name)
                        encrypted = encrypt_pdf_bytes(raw, password)
                        # choose safe name: keep original name but add _protected
                        base = os.path.basename(name)
                        folder = os.path.dirname(name)
                        if base.lower().endswith('.pdf'):
                            base_n = base[:-4] + '_protected.pdf'
                        else:
                            base_n = base + '_protected.pdf'
                        out_name = os.path.join(folder, base_n) if folder else base_n
                        # zipinfo: ensure correct path separators
                        out_zip.writestr(out_name.replace('\\', '/'), encrypted)
                    except Exception as e:
                        # skip corrupt PDF (optionally we could include an error file)
                        print(f"Failed to encrypt {name}: {e}")
                        continue
                else:
                    # skip non-pdfs
                    continue

        if not pdf_found:
            return jsonify({'error': 'No PDF files found inside the ZIP.'}), 400

        out_buffer.seek(0)
        zip_filename = filename
        if zip_filename.lower().endswith('.zip'):
            zip_filename = zip_filename[:-4]
        zip_filename = f"{zip_filename}_protected.zip"

        return send_file(
            out_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
    else:
        return jsonify({'error': 'Unsupported file type. Upload a PDF or ZIP'}), 400

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
