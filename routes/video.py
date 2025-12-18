# Video routes - Endpoints for video processing operations
from flask import Blueprint, request, jsonify
import os
import sys

video_bp = Blueprint("video", __name__)

# Add parent directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Lazy loading for heavy modules


@video_bp.route("/video-upscale", methods=["POST", "OPTIONS"])
def video_upscale():
    """Upscale video using FFmpeg"""
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from videoupscale import video_upscale as _video_upscale_original
    return _video_upscale_original()


@video_bp.route("/download-video-batch", methods=["POST", "OPTIONS"])
def download_video_batch():
    """Download videos from URLs (single or batch from file)"""
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    from downloadvideolink_batch import download_video_batch as _download_batch_original
    return _download_batch_original()
