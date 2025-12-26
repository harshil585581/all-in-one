from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import yt_dlp
import os
import zipfile
import tempfile
import shutil
from pathlib import Path
import concurrent.futures
import docx
import PyPDF2
import re
import sys
import subprocess

# Lazy import for heavy library - loaded only when needed
_VideoFileClip = None

def _ensure_moviepy():
    """Lazy load moviepy only when needed"""
    global _VideoFileClip
    if _VideoFileClip is None:
        from moviepy.editor import VideoFileClip
        _VideoFileClip = VideoFileClip
    return _VideoFileClip

def find_ffmpeg():
    """Find FFmpeg executable path - works on Windows, Linux, and macOS"""
    import shutil
    
    # Use shutil.which() to get absolute path - most reliable
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return ffmpeg_path
    
    
    # Common installation paths
    common_paths = [
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe',
        'C:\\ffmpeg\\bin\\ffmpeg.exe',
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    return None

def verify_ffmpeg():
    """Verify FFmpeg is available and log its location"""
    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path:
        print(f"[FFmpeg] Found at: {ffmpeg_path}")
        return ffmpeg_path
    else:
        print("[FFmpeg] WARNING: FFmpeg not found in system PATH!")
        print("[FFmpeg] Audio extraction may fail without FFmpeg")
        return None

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "http://localhost:4200"}})

# Temporary directory for downloads
TEMP_DIR = tempfile.gettempdir()

def extract_urls_from_text(text):
    """Extract URLs from text content."""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    
    # Also split by lines and clean
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line and (line.startswith('http://') or line.startswith('https://')):
            if line not in urls:
                urls.append(line)
    
    return [url.strip() for url in urls if url.strip()]

def extract_urls_from_docx(file_path):
    """Extract URLs from DOCX file."""
    try:
        doc = docx.Document(file_path)
        text = '\n'.join([paragraph.text for paragraph in doc.paragraphs])
        return extract_urls_from_text(text)
    except Exception as e:
        print(f"Error reading DOCX: {e}")
        return []

def extract_urls_from_pdf(file_path):
    """Extract URLs from PDF file."""
    try:
        urls = []
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    urls.extend(extract_urls_from_text(text))
        return urls
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return []

def sanitize_filename(filename):
    """Remove invalid characters from filename."""
    # Remove invalid characters for Windows/Unix filesystems
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip('. ')
    return sanitized if sanitized else 'audio'

def download_audio(url, output_dir):
    """
    Download audio from a video URL using yt-dlp.
    Requires FFmpeg for audio extraction and format conversion.
    Returns the path to the downloaded audio file or None if failed.
    """
    try:
        # Create a unique subdirectory for this download
        download_id = os.urandom(8).hex()
        download_dir = os.path.join(output_dir, download_id)
        os.makedirs(download_dir, exist_ok=True)
        
        # Find FFmpeg location
        ffmpeg_location = find_ffmpeg()
        
        # yt-dlp options for audio extraction
        # Strategy: If FFmpeg available, extract and convert. If not, download best audio as-is.
        ydl_opts = {
            # Format selector: Get best audio quality available
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            # Universal settings that work across all platforms
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'nocheckcertificate': True,
            # Retries for better reliability
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            # Platform-specific optimizations (applied only when needed)
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                },
                'instagram': {
                    'username': None,  # Can be configured if needed
                    'password': None,
                }
            },
            # HTTP headers for better compatibility
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            },
        }
        
        # Configure FFmpeg-based processing if available
        if ffmpeg_location:
            # FFmpeg is available - extract and convert to M4A
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '192',
                'nopostoverwrites': False,
            }]
            ydl_opts['ffmpeg_location'] = ffmpeg_location
            print(f"[DEBUG] Using FFmpeg at: {ffmpeg_location} for audio conversion")
        else:
            # No FFmpeg - download audio in native format (no conversion)
            print("[WARNING] FFmpeg not found - downloading audio in native format (no conversion)")
            # No postprocessors - just download the audio stream as-is
        
        print(f"Downloading audio from: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Get the actual filename
            if info:
                # The output file will be in the download_dir
                files = os.listdir(download_dir)
                
                # Look for common audio formats
                audio_extensions = ['.m4a', '.opus', '.webm', '.mp3', '.aac', '.ogg', '.wav', '.mp4']
                audio_files = [f for f in files if any(f.endswith(ext) for ext in audio_extensions)]
                
                if audio_files:
                    original_path = os.path.join(download_dir, audio_files[0])
                    
                    # Sanitize filename and move to output_dir
                    safe_filename = sanitize_filename(audio_files[0])
                    final_path = os.path.join(output_dir, safe_filename)
                    
                    # Handle duplicate filenames
                    counter = 1
                    base_name, ext = os.path.splitext(safe_filename)
                    while os.path.exists(final_path):
                        safe_filename = f"{base_name}_{counter}{ext}"
                        final_path = os.path.join(output_dir, safe_filename)
                        counter += 1
                    
                    shutil.move(original_path, final_path)
                    
                    # Clean up download directory
                    shutil.rmtree(download_dir, ignore_errors=True)
                    
                    print(f"Audio extracted successfully: {safe_filename}")
                    return final_path
        
        # Clean up if no file was found
        shutil.rmtree(download_dir, ignore_errors=True)
        return None
        
    except Exception as e:
        print(f"[ERROR] Error downloading audio from {url}: {e}")
        import traceback
        print(f"[ERROR] Full traceback:")
        traceback.print_exc()
        # Clean up on error
        if 'download_dir' in locals() and os.path.exists(download_dir):
            shutil.rmtree(download_dir, ignore_errors=True)
        return None

def extract_audio_from_video(video_path, output_dir):
    """
    Extract audio from an uploaded video file using MoviePy.
    Returns the path to the extracted audio file or None if failed.
    """
    try:
        # Lazy load moviepy
        VideoFileClip = _ensure_moviepy()
        
        print(f"[DEBUG] Starting audio extraction from video: {video_path}")
        print(f"[DEBUG] Video file exists: {os.path.exists(video_path)}")
        print(f"[DEBUG] Video file size: {os.path.getsize(video_path)} bytes")
        
        # Load video file
        try:
            video = VideoFileClip(video_path)
            print(f"[DEBUG] Video loaded successfully. Duration: {video.duration}s")
        except Exception as load_error:
            print(f"[ERROR] Failed to load video file: {load_error}")
            print(f"[ERROR] This might be due to missing FFmpeg or unsupported codec")
            raise
        
        # Get original filename without extension
        original_name = Path(video_path).stem
        safe_filename = sanitize_filename(original_name)
        
        # Output audio as MP3 (widely compatible format)
        audio_filename = f"{safe_filename}.mp3"
        audio_path = os.path.join(output_dir, audio_filename)
        
        # Handle duplicate filenames
        counter = 1
        while os.path.exists(audio_path):
            audio_filename = f"{safe_filename}_{counter}.mp3"
            audio_path = os.path.join(output_dir, audio_filename)
            counter += 1
        
        print(f"[DEBUG] Output audio path: {audio_path}")
        
        # Extract audio
        if video.audio is not None:
            print(f"[DEBUG] Audio track found, extracting...")
            try:
                # Use libmp3lame codec (more compatible than 'mp3')
                video.audio.write_audiofile(
                    audio_path, 
                    codec='libmp3lame',
                    bitrate='192k',
                    verbose=False, 
                    logger=None
                )
                video.close()
                print(f"[SUCCESS] Audio extracted successfully: {audio_filename}")
                print(f"[DEBUG] Output file size: {os.path.getsize(audio_path)} bytes")
                return audio_path
            except Exception as write_error:
                video.close()
                print(f"[ERROR] Failed to write audio file: {write_error}")
                print(f"[ERROR] Make sure FFmpeg is installed and accessible")
                raise
        else:
            video.close()
            print(f"[WARNING] No audio track found in video: {video_path}")
            return None
            
    except Exception as e:
        print(f"[ERROR] Error extracting audio from video {video_path}: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_audio_mimetype(filename):
    """Get MIME type based on file extension."""
    ext = Path(filename).suffix.lower()
    mimetypes = {
        '.m4a': 'audio/mp4',
        '.mp4': 'audio/mp4',
        '.mp3': 'audio/mpeg',
        '.opus': 'audio/opus',
        '.webm': 'audio/webm',
        '.ogg': 'audio/ogg',
        '.aac': 'audio/aac',
        '.wav': 'audio/wav',
    }
    return mimetypes.get(ext, 'audio/mpeg')

@app.route('/download-audio-batch', methods=['POST', 'OPTIONS'])
def download_audio_batch():
    """
    Extract audio from video URLs.
    Accepts either:
    - A single URL via 'url' form field
    - A file (.txt, .docx, .pdf) with multiple URLs via 'file' form field
    
    Returns:
    - Single audio file for single URL (format: m4a, opus, webm, etc.)
    - ZIP file containing multiple audio files for file upload
    """
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        print("=" * 60)
        print("[DEBUG] Received request to /download-audio-batch")
        print(f"[DEBUG] Request method: {request.method}")
        print(f"[DEBUG] Request headers: {dict(request.headers)}")
        print(f"[DEBUG] Form data keys: {list(request.form.keys())}")
        print(f"[DEBUG] Files in request: {list(request.files.keys())}")
        print("=" * 60)
        
        urls = []
        video_files = []  # For uploaded video files
        
        # Check if URL was provided
        if 'url' in request.form:
            url = request.form['url'].strip()
            if url:
                urls.append(url)
        
        # Check if file was provided
        elif 'file' in request.files:
            file = request.files['file']
            
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            # Save uploaded file temporarily
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix)
            file.save(temp_file.name)
            temp_file.close()
            
            # Extract URLs based on file type
            file_ext = Path(file.filename).suffix.lower()
            print(f"[DEBUG] Uploaded file: {file.filename}")
            print(f"[DEBUG] File extension: {file_ext}")
            print(f"[DEBUG] Temp file path: {temp_file.name}")
            
            # Check if it's a video file
            video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
            
            if file_ext in video_extensions:
                # It's a video file - add to video_files list
                print(f"[DEBUG] Detected as video file, adding to processing queue")
                video_files.append(temp_file.name)

            
            elif file_ext == '.txt':
                with open(temp_file.name, 'r', encoding='utf-8') as f:
                    content = f.read()
                    urls = extract_urls_from_text(content)
                # Clean up temp file
                os.unlink(temp_file.name)
            
            elif file_ext == '.docx':
                urls = extract_urls_from_docx(temp_file.name)
                # Clean up temp file
                os.unlink(temp_file.name)
            
            elif file_ext == '.pdf':
                urls = extract_urls_from_pdf(temp_file.name)
                # Clean up temp file
                os.unlink(temp_file.name)
            
            else:
                os.unlink(temp_file.name)
                return jsonify({'error': f'Unsupported file type: {file_ext}'}), 400
        
        else:
            return jsonify({'error': 'No URL or file provided'}), 400
        
        if not urls and not video_files:
            return jsonify({'error': 'No valid URLs or video files found'}), 400
        
        # Remove duplicates while preserving order
        urls = list(dict.fromkeys(urls))
        
        print(f"Found {len(urls)} URL(s) and {len(video_files)} video file(s) to process")
        
        # Create temporary directory for downloads
        temp_download_dir = tempfile.mkdtemp(prefix='audio_download_')
        
        try:
            # Download audio files (with parallel processing for multiple URLs)
            audio_files = []
            
            # Process video files first
            for video_file in video_files:
                audio_path = extract_audio_from_video(video_file, temp_download_dir)
                if audio_path:
                    audio_files.append(audio_path)
                # Clean up the temporary video file
                try:
                    os.unlink(video_file)
                except:
                    pass
            
            # Process URLs
            if len(urls) == 1 and not video_files:
                # Single URL - direct download
                audio_path = download_audio(urls[0], temp_download_dir)
                if audio_path:
                    audio_files.append(audio_path)
            elif urls:
                # Multiple URLs - parallel download
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    future_to_url = {executor.submit(download_audio, url, temp_download_dir): url for url in urls}
                    
                    for future in concurrent.futures.as_completed(future_to_url):
                        url = future_to_url[future]
                        try:
                            audio_path = future.result()
                            if audio_path:
                                audio_files.append(audio_path)
                        except Exception as e:
                            print(f"Error processing {url}: {e}")
            
            if not audio_files:
                shutil.rmtree(temp_download_dir, ignore_errors=True)
                return jsonify({'error': 'Failed to extract audio from any of the provided sources'}), 500
            
            # If single audio file, return it directly
            if len(audio_files) == 1:
                audio_file = audio_files[0]
                filename = os.path.basename(audio_file)
                mimetype = get_audio_mimetype(filename)
                
                response = send_file(
                    audio_file,
                    as_attachment=True,
                    download_name=filename,
                    mimetype=mimetype
                )
                
                # Schedule cleanup after sending
                @response.call_on_close
                def cleanup():
                    shutil.rmtree(temp_download_dir, ignore_errors=True)
                
                return response
            
            # Multiple audio files - create ZIP
            zip_filename = f'audio_files_{len(audio_files)}_files.zip'
            zip_path = os.path.join(temp_download_dir, zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for audio_file in audio_files:
                    zipf.write(audio_file, os.path.basename(audio_file))
            
            response = send_file(
                zip_path,
                as_attachment=True,
                download_name=zip_filename,
                mimetype='application/zip'
            )
            
            # Schedule cleanup after sending
            @response.call_on_close
            def cleanup():
                shutil.rmtree(temp_download_dir, ignore_errors=True)
            
            return response
        
        except Exception as e:
            # Clean up on error
            shutil.rmtree(temp_download_dir, ignore_errors=True)
            raise e
    
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Error in download_audio_batch: {error_msg}")
        import traceback
        print("[ERROR] Full traceback:")
        traceback.print_exc()
        
        # Return detailed error for debugging
        return jsonify({
            'error': error_msg,
            'type': type(e).__name__,
            'details': 'Check server logs for full traceback'
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'service': 'Audio Extractor API (No FFmpeg)'}), 200

if __name__ == '__main__':
    print("=" * 60)
    print("Audio Extractor Backend Service")
    print("=" * 60)
    print("Starting Flask server on http://127.0.0.1:5000")
    print("Audio formats: M4A, OPUS, WEBM (native, with FFmpeg conversion)")
    print("Supported platforms: YouTube, Instagram, Twitter, TikTok, Facebook, and 1000+ more sites")
    print("Endpoint: POST /download-audio-batch")
    print("=" * 60)
    app.run(debug=True, host='127.0.0.1', port=5000)