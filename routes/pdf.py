# PDF routes - Endpoints for PDF processing operations
from flask import Blueprint, request, jsonify
import os
import sys

pdf_bp = Blueprint("pdf", __name__)

# Add parent directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Lazy loading for heavy modules


@pdf_bp.route("/protect-pdf", methods=["POST", "OPTIONS"])
def protect_pdf():
    """Add password protection to PDF files"""
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from pdfprotection import protect_pdf as _protect_pdf_original
    return _protect_pdf_original()


@pdf_bp.route("/unlock-pdf", methods=["POST", "OPTIONS"])
def unlock_pdf():
    """Remove password protection from PDF files"""
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from unlockpdf import unlock_pdf as _unlock_pdf_original
    return _unlock_pdf_original()


@pdf_bp.route("/pdf-to-word", methods=["POST", "OPTIONS"])
def pdf_to_word():
    """Convert PDF to Word document"""
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from pdftoword import convert_pdf_to_word as _pdf_to_word_original
    return _pdf_to_word_original()


@pdf_bp.route("/watermark-files", methods=["POST", "OPTIONS"])
def watermark_files():
    """Add watermark to PDF files"""
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from watermarkfiles import watermark_files as _watermark_files_original
    return _watermark_files_original()