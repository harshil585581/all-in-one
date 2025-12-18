# Conversion routes - Endpoints for file conversion operations
from flask import Blueprint, request, jsonify
import os
import sys

conversion_bp = Blueprint("conversion", __name__)

# Add parent directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Lazy loading for heavy modules


@conversion_bp.route("/file-pdf", methods=["POST", "OPTIONS"])
def file_pdf():
    """Convert various file formats to PDF"""
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from filestopdf import file_pdf as _file_pdf_original
    return _file_pdf_original()


@conversion_bp.route("/status", methods=["GET"])
def status():
    """Status endpoint for conversion service"""
    from filestopdf import status as _status_original
    return _status_original()


@conversion_bp.route("/convert-all-to-ppt", methods=["POST", "OPTIONS"])
def convert_to_ppt():
    """Convert files to PowerPoint format"""
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from filestoppt import convert_all_to_ppt as _to_ppt_original
    return _to_ppt_original()


@conversion_bp.route("/compress", methods=["POST", "OPTIONS"])
def compress():
    """Compress various file types"""
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from filescompressor import compress_endpoint as _compress_original
    return _compress_original()
