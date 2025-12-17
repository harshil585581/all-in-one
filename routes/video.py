# Video routes - Endpoints for video processing operations
from flask import Blueprint
import os
import sys

video_bp = Blueprint("video", __name__)

# Add parent directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from existing files
from videoupscale import video_upscale as _video_upscale_original
from downloadvideolink_batch import download_video_batch as _download_batch_original


@video_bp.route("/video-upscale", methods=["POST"])
def video_upscale():
    """Upscale video using FFmpeg"""
    return _video_upscale_original()


@video_bp.route("/download-video-batch", methods=["POST"])
def download_video_batch():
    """Download videos from URLs (single or batch from file)"""
    return _download_batch_original()
