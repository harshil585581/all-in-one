#!/usr/bin/env python3
import os
import io
import zipfile
import tempfile
import shutil
import traceback
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from pdf2docx import parse
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Allow larger uploads (adjust as needed)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB
CORS(app, resources={r"/*": {"origins": "*"}})  # allow requests from any origin (adjust for production)

@app.route('/pdf-to-word', methods=['POST'])
def convert_pdf_to_word():
    """API endpoint to convert PDF(s) to Word document(s)."""
    print("\n" + "="*60)
    print("📥 NEW CONVERSION REQUEST")
    print("="*60)

    try:
        if 'file' not in request.files:
            print("❌ ERROR: No file in request")
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            print("❌ ERROR: Empty filename")
            return jsonify({'error': 'No file selected'}), 400

        filename = secure_filename(file.filename)
        print(f"📄 File received: {filename}")

        if filename.lower().endswith('.pdf'):
            print("🔄 Processing single PDF file...")
            return handle_single_pdf(file, filename)

        elif filename.lower().endswith('.zip'):
            print("🔄 Processing ZIP file...")
            return handle_zip_file(file, filename)

        else:
            print(f"❌ ERROR: Invalid file type: {filename}")
            return jsonify({'error': 'Invalid file type. Please upload a PDF or ZIP file'}), 400

    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def handle_single_pdf(file, filename):
    temp_dir = tempfile.mkdtemp()
    try:
        pdf_path = os.path.join(temp_dir, filename)
        file.save(pdf_path)
        print(f"   ✓ PDF saved: {pdf_path}")

        docx_filename = os.path.splitext(filename)[0] + ".docx"
        docx_path = os.path.join(temp_dir, docx_filename)

        print(f"   🔄 Converting to Word...")
        # parse(src_file, dest_file)
        parse(pdf_path, docx_path)
        print(f"   ✓ Conversion complete: {docx_filename}")

        # return as attachment
        return send_file(
            docx_path,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=docx_filename
        )

    except Exception as e:
        print(f"   ❌ Error in single PDF conversion: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        # cleanup
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

def handle_zip_file(file, filename):
    temp_dir = tempfile.mkdtemp()
    try:
        zip_path = os.path.join(temp_dir, filename)
        file.save(zip_path)
        print(f"   ✓ ZIP saved: {zip_path}")

        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        print(f"   ✓ ZIP extracted")

        # find pdfs
        pdf_files = []
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                if f.lower().endswith('.pdf'):
                    pdf_files.append(os.path.join(root, f))

        if not pdf_files:
            print("   ❌ No PDF files found in ZIP")
            return jsonify({'error': 'No PDF files found in the ZIP'}), 400

        print(f"   ✓ Found {len(pdf_files)} PDF file(s)")

        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        for i, pdf_path in enumerate(pdf_files, 1):
            pdf_name = os.path.basename(pdf_path)
            docx_name = os.path.splitext(pdf_name)[0] + ".docx"
            docx_path = os.path.join(output_dir, docx_name)
            try:
                print(f"   🔄 [{i}/{len(pdf_files)}] Converting: {pdf_name}")
                parse(pdf_path, docx_path)
                print(f"      ✓ Done: {docx_name}")
            except Exception as e:
                print(f"      ❌ Failed: {pdf_name} - {str(e)}")
                traceback.print_exc()
                # continue converting other files

        # create zip of converted docx files
        output_zip_path = os.path.join(temp_dir, "converted_documents.zip")
        with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_out:
            for root, dirs, files in os.walk(output_dir):
                for f in files:
                    file_path = os.path.join(root, f)
                    arcname = os.path.relpath(file_path, output_dir)
                    zip_out.write(file_path, arcname)
                    print(f"   ✓ Added to ZIP: {arcname}")

        return send_file(
            output_zip_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name='converted_documents.zip'
        )

    except Exception as e:
        print(f"   ❌ Error in ZIP conversion: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'PDF to Word Converter is running',
        'version': '2.0 - WORKING'
    }), 200

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 PDF to Word Converter - BACKEND (no HTML)")
    print("="*60)
    print("📍 Server: http://127.0.0.1:5000")
    print("📍 Health: http://127.0.0.1:5000/health")
    print("📍 Convert: POST /pdf-to-word")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
