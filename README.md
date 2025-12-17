# Upscale Fullstack Backend

Unified Flask backend service with modular architecture for image, video, audio, PDF processing and file conversions.

## Quick Start

### Run the Server

```bash
python app.py
```

Server will start on `http://127.0.0.1:5000`

### Check Status

```bash
# API index with all endpoints
curl http://127.0.0.1:5000/

# Health check
curl http://127.0.0.1:5000/health
```

## API Endpoints

### Image Processing

- `POST /img-compress` - Compress images
- `POST /img-jpg` - Convert to JPG
- `POST /img-png` - Convert to PNG
- `POST /img-webp` - Convert to WEBP
- `POST /upscale` - Upscale images
- `POST /remove-imgbg` - Remove background
- `POST /watermark-imgvideo` - Add watermark

### Video Processing

- `POST /video-upscale` - Upscale videos
- `POST /download-video-batch` - Download from URLs

### Audio Processing

- `POST /download-audio-batch` - Extract audio from videos

### PDF Operations

- `POST /protect-pdf` - Add password protection
- `POST /unlock-pdf` - Remove password
- `POST /pdf-to-word` - Convert to Word
- `POST /watermark-files` - Add watermark

### File Conversions

- `POST /file-pdf` - Convert to PDF
- `POST /convert-all-to-ppt` - Convert to PowerPoint
- `POST /compress` - Compress files
- `GET /status` - Service status

## Project Structure

```
backend/
├── app.py              # Main entry point
├── routes/             # API route handlers
│   ├── image.py
│   ├── video.py
│   ├── audio.py
│   ├── pdf.py
│   └── conversion.py
├── services/           # Business logic
│   └── image_service.py
├── utils/              # Shared utilities
│   └── helpers.py
├── temp/               # Temporary files
└── uploads/            # File uploads
```

## Configuration

### CORS

Currently allows all origins. Update in `app.py` for production:

```python
CORS(app, resources={r"/*": {
    "origins": "https://your-domain.com",
    ...
}})
```

### Max Upload Size

Default: 500MB. Change in `app.py`:

```python
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
```

### Debug Mode

For production, set `debug=False` in `app.py`:

```python
app.run(host='127.0.0.1', port=5000, debug=False)
```

## Requirements

See `requirements.txt` for dependencies:

- Flask
- flask-cors
- Pillow
- yt-dlp
- moviepy
- PyPDF2
- rembg
- And more...

Install with:

```bash
pip install -r requirements.txt
```

## Notes

All endpoint URLs remain unchanged from the original implementation for backward compatibility with existing frontends.
