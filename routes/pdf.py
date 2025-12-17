# PDF routes - Endpoints for PDF processing operations
from flask import Blueprint
import os
import sys

pdf_bp = Blueprint("pdf", __name__)

# Add parent directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from existing files
from pdfprotection import protect_pdf as _protect_pdf_original
from unlockpdf import unlock_pdf as _unlock_pdf_original
from pdftoword import convert_pdf_to_word as _pdf_to_word_original
from watermarkfiles import watermark_files as _watermark_files_original


@pdf_bp.route("/protect-pdf", methods=["POST"])
def protect_pdf():
    """Add password protection to PDF files"""
    return _protect_pdf_original()


@pdf_bp.route("/unlock-pdf", methods=["POST"])
def unlock_pdf():
    """Remove password protection from PDF files"""
    return _unlock_pdf_original()


@pdf_bp.route("/pdf-to-word", methods=["POST"])
def pdf_to_word():
    """Convert PDF to Word document"""
    return _pdf_to_word_original()


@pdf_bp.route("/watermark-files", methods=["POST"])
def watermark_files():
    """Add watermark to PDF files"""
    return _watermark_files_original()
