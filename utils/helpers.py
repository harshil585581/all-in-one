# Shared utility functions for file handling and validation

import os
import re
from typing import Set


def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from filename."""
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    # Limit length
    if len(filename) > 255:
        filename = filename[:255]
    return filename or 'file'


def get_file_extension(filename: str) -> str:
    """Extract file extension in lowercase."""
    return os.path.splitext(filename.lower())[1]


def is_allowed_extension(filename: str, allowed_extensions: Set[str]) -> bool:
    """Check if file extension is in allowed list."""
    ext = get_file_extension(filename)
    return ext in allowed_extensions


def get_mimetype_from_extension(ext: str) -> str:
    """Get MIME type based on file extension."""
    mime_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.tiff': 'image/tiff',
        '.tif': 'image/tiff',
        '.mp4': 'video/mp4',
        '.mov': 'video/quicktime',
        '.avi': 'video/x-msvideo',
        '.mkv': 'video/x-matroska',
        '.webm': 'video/webm',
        '.pdf': 'application/pdf',
        '.zip': 'application/zip',
        '.m4a': 'audio/mp4',
        '.mp3': 'audio/mpeg',
        '.opus': 'audio/opus',
        '.ogg': 'audio/ogg',
    }
    return mime_map.get(ext.lower(), 'application/octet-stream')
