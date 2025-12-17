# Audio routes - Endpoints for audio processing operations
from flask import Blueprint
import os
import sys

audio_bp = Blueprint("audio", __name__)

# Add parent directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from existing files
from audioextractor import download_audio_batch as _download_audio_original


@audio_bp.route("/download-audio-batch", methods=["POST", "OPTIONS"])
def download_audio_batch():
    """Extract audio from video URLs (single or batch from file)"""
    return _download_audio_original()
