# downloadvideolink_batch.py - ULTRA-FAST VERSION
from flask import request, send_file, jsonify
import yt_dlp
import os
import tempfile
import shutil
import zipfile
from pathlib import Path
import re
import PyPDF2
from docx import Document
import logging
from functools import wraps
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MAX_URLS = 50
MAX_FILE_SIZE_MB = 100
DOWNLOAD_TIMEOUT = 300
ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.docx'}

def find_ffmpeg():
    """Find FFmpeg executable"""
    import shutil as sh
    ffmpeg = sh.which('ffmpeg')
    if ffmpeg:
        return ffmpeg
    
    paths = ['/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg', 
             'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe', 'C:\\ffmpeg\\bin\\ffmpeg.exe']
    
    for p in paths:
        if os.path.exists(p):
            return p
    return None

def validate_url(url):
    """Validate URL format"""
    if not url or not isinstance(url, str):
        return False
    url_pattern = r'^https?://'
    return bool(re.match(url_pattern, url.strip()))

def sanitize_filename(filename):
    """Sanitize filename to prevent directory traversal"""
    safe_chars = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.'))
    return safe_chars[:255]

def extract_urls_from_text(text):
    """Extract URLs from text"""
    try:
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
        return [u.strip() for u in urls if validate_url(u)]
    except Exception as e:
        logger.error(f"Error extracting URLs from text: {e}")
        return []

def extract_urls_from_txt(path):
    """Extract URLs from .txt file"""
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return extract_urls_from_text(f.read())
    except Exception as e:
        logger.error(f"Error reading txt file: {e}")
        return []

def extract_urls_from_pdf(path):
    """Extract URLs from .pdf file"""
    urls = []
    try:
        with open(path, 'rb') as f:
            pdf = PyPDF2.PdfReader(f)
            for page in pdf.pages:
                try:
                    text = page.extract_text()
                    urls.extend(extract_urls_from_text(text))
                except Exception as e:
                    logger.warning(f"Error extracting from PDF page: {e}")
                    continue
    except Exception as e:
        logger.error(f"Error reading PDF file: {e}")
    return urls

def extract_urls_from_docx(path):
    """Extract URLs from .docx file"""
    urls = []
    try:
        doc = Document(path)
        for para in doc.paragraphs:
            try:
                urls.extend(extract_urls_from_text(para.text))
            except Exception as e:
                logger.warning(f"Error extracting from DOCX paragraph: {e}")
                continue
    except Exception as e:
        logger.error(f"Error reading DOCX file: {e}")
    return urls

def select_format_by_quality(formats, target_quality):
    """Select best format ID based on target quality"""
    try:
        quality_heights = {
            '2160p': 2160, '1440p': 1440, '1080p': 1080, '720p': 720,
            '480p': 480, '360p': 360, '240p': 240, '144p': 144, 'best': 9999
        }
        
        target_height = quality_heights.get(target_quality, 9999)
        
        # Filter video formats
        video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('height')]
        
        if not video_formats:
            return None
        
        # Find suitable formats
        suitable = [f for f in video_formats if f.get('height', 0) <= target_height]
        
        if not suitable:
            suitable = sorted(video_formats, key=lambda x: x.get('height', 0))
            return suitable[0]['format_id'] if suitable else None
        
        # Get best quality at or below target
        best = max(suitable, key=lambda x: (x.get('height', 0), x.get('tbr', 0)))
        return best['format_id']
    except Exception as e:
        logger.error(f"Error selecting format: {e}")
        return None

def detect_platform(url):
    """Detect video platform from URL"""
    url_lower = url.lower()
    
    platforms = {
        'youtube': ['youtube.com', 'youtu.be'],
        'twitter': ['twitter.com', 'x.com', 't.co'],
        'instagram': ['instagram.com', 'instagr.am'],
        'facebook': ['facebook.com', 'fb.watch', 'fb.com'],
        'tiktok': ['tiktok.com', 'vm.tiktok.com'],
        'reddit': ['reddit.com', 'redd.it', 'v.redd.it'],
        'vimeo': ['vimeo.com'],
        'dailymotion': ['dailymotion.com', 'dai.ly'],
        'twitch': ['twitch.tv', 'clips.twitch.tv'],
        'linkedin': ['linkedin.com'],
        'snapchat': ['snapchat.com'],
        'pinterest': ['pinterest.com', 'pin.it'],
        'tumblr': ['tumblr.com'],
        'streamable': ['streamable.com'],
        'imgur': ['imgur.com'],
        'soundcloud': ['soundcloud.com'],
        'spotify': ['spotify.com'],
        'bandcamp': ['bandcamp.com'],
    }
    
    for platform, domains in platforms.items():
        if any(domain in url_lower for domain in domains):
            return platform
    
    return 'generic'

def get_platform_optimized_options(platform, quality='best'):
    """Get platform-specific optimized download options"""
    
    # Base ultra-fast options for all platforms
    base_opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 15,
        'retries': 2,
        'fragment_retries': 2,
        'extractor_retries': 1,
        'concurrent_fragment_downloads': 16,
        'http_chunk_size': 20971520,
        'buffersize': 65536,
        'throttledratelimit': None,
        'ratelimit': None,
        'noprogress': True,
        'prefer_insecure': True,
        'no_check_certificates': True,
        'extract_flat': False,
        'lazy_playlist': True,
        'no_color': True,
        'geo_bypass': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        },
    }
    
    # Platform-specific optimizations
    platform_opts = {
        'youtube': {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
        },
        'twitter': {
            'format': 'best',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://twitter.com/',
            },
        },
        'instagram': {
            'format': 'best',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15',
                'Referer': 'https://www.instagram.com/',
            },
        },
        'facebook': {
            'format': 'best',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            },
        },
        'tiktok': {
            'format': 'best',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.tiktok.com/',
            },
        },
        'reddit': {
            'format': 'best',
            'merge_output_format': 'mp4',
        },
        'vimeo': {
            'format': 'best[ext=mp4]/best',
            'http_headers': {
                'Referer': 'https://vimeo.com/',
            },
        },
        'twitch': {
            'format': 'best',
            'http_headers': {
                'Client-ID': 'kimne78kx3ncx6brgo4mv6wki5h1ko',
            },
        },
        'snapchat': {
            'format': 'best',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15',
            },
        },
    }
    
    # Merge base with platform-specific options
    opts = base_opts.copy()
    if platform in platform_opts:
        opts.update(platform_opts[platform])
        logger.info(f"Using {platform} optimized settings")
    else:
        opts['format'] = 'best'
        logger.info(f"Using generic settings for {platform}")
    
    return opts

def download_single_video(url, output_dir, index=0, quality='best'):
    """Download video with MAXIMUM SPEED optimization - UNIVERSAL PLATFORM SUPPORT"""
    temp_files = []
    
    try:
        if not validate_url(url):
            logger.warning(f"Invalid URL: {url}")
            return {'success': False, 'error': 'Invalid URL'}
        
        # Detect platform
        platform = detect_platform(url)
        logger.info(f"Platform detected: {platform}")
        
        output_template = os.path.join(output_dir, f'video_{index}.%(ext)s')
        ffmpeg = find_ffmpeg()
        
        logger.info(f"Downloading {quality}: {url[:60]}...")
        start_time = time.time()
        
        # Extract info (FAST)
        info_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'socket_timeout': 15,
            'extractor_retries': 1,
            'geo_bypass': True,
        }
        
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return {'success': False, 'error': 'Cannot extract video info'}
            
            formats = info.get('formats', [])
            
            # For platforms with quality selection (mainly YouTube)
            format_string = None
            if platform == 'youtube' and formats:
                # Select format
                video_format_id = select_format_by_quality(formats, quality)
                
                if video_format_id:
                    # Get audio
                    audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                    audio_format_id = None
                    if audio_formats:
                        best_audio = max(audio_formats, key=lambda x: x.get('abr', 0))
                        audio_format_id = best_audio['format_id']
                    
                    # Construct format string
                    format_string = f"{video_format_id}+{audio_format_id}" if audio_format_id else video_format_id
                    logger.info(f"Format: {format_string}")
            
            # For other platforms, use best available
            if not format_string:
                format_string = 'best'
                logger.info(f"Using best available format for {platform}")
            
            # Get platform-optimized options
            download_opts = get_platform_optimized_options(platform, quality)
            download_opts['format'] = format_string
            download_opts['outtmpl'] = output_template
            download_opts['merge_output_format'] = 'mp4'
            
            # FFMPEG SPEED OPTIMIZATION
            download_opts['postprocessor_args'] = {
                'ffmpeg': [
                    '-preset', 'ultrafast',  # Fastest encoding
                    '-threads', '0',  # Use all CPU cores
                    '-movflags', '+faststart',  # Web optimization
                ]
            }
            
            # Add cookies support for platforms that need it
            download_opts['cookiefile'] = None  # Can be set if needed
            
            if ffmpeg:
                download_opts['ffmpeg_location'] = ffmpeg
            
            with yt_dlp.YoutubeDL(download_opts) as ydl_download:
                ydl_download.download([url])
            
            # Find file (check multiple extensions)
            filename = output_template.replace('%(ext)s', 'mp4')
            
            if not os.path.exists(filename):
                possible_exts = ['.webm', '.mkv', '.mp4', '.mov', '.avi', '.flv', '.m4v', '.ts']
                for ext in possible_exts:
                    test_file = output_template.replace('%(ext)s', ext[1:])
                    if os.path.exists(test_file):
                        filename = test_file
                        break
            
            if not os.path.exists(filename):
                return {'success': False, 'error': 'Downloaded file not found'}
            
            temp_files.append(filename)
            
            # Validate file
            size_mb = os.path.getsize(filename) / (1024 * 1024)
            if size_mb == 0:
                return {'success': False, 'error': 'Downloaded file is empty'}
            
            # Sanitize title
            title = info.get('title', f'video_{index}')
            safe_title = sanitize_filename(title)[:50]
            
            # Rename
            ext = os.path.splitext(filename)[1]
            new_name = os.path.join(output_dir, f'{safe_title}{ext}')
            
            counter = 1
            base_name = new_name
            while os.path.exists(new_name):
                new_name = f"{os.path.splitext(base_name)[0]}_{counter}{ext}"
                counter += 1
            
            if filename != new_name:
                shutil.move(filename, new_name)
                filename = new_name
            
            elapsed = time.time() - start_time
            speed_mbps = (size_mb * 8) / elapsed if elapsed > 0 else 0
            
            logger.info(f"Success [{platform}]: {size_mb:.1f}MB in {elapsed:.1f}s ({speed_mbps:.1f} Mbps) - {os.path.basename(filename)}")
            
            return {
                'success': True,
                'filename': filename,
                'title': safe_title,
                'filesize_mb': size_mb,
                'download_time': elapsed,
                'platform': platform
            }
            
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except:
                pass
        return {'success': False, 'error': str(e)}

def download_video_batch():
    """Main endpoint - ULTRA-FAST VERSION"""
    temp_dir = None
    
    try:
        urls = []
        quality = request.form.get('quality', 'best').lower()
        
        # Validate quality
        valid_qualities = ['2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p', 'best']
        if quality not in valid_qualities:
            quality = 'best'
        
        logger.info(f"Request: quality={quality}")
        
        # Handle file upload
        if 'file' in request.files:
            uploaded_file = request.files['file']
            
            if not uploaded_file.filename:
                return jsonify({'error': 'No file selected'}), 400
            
            file_ext = os.path.splitext(uploaded_file.filename.lower())[1]
            if file_ext not in ALLOWED_EXTENSIONS:
                return jsonify({'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
            
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, sanitize_filename(uploaded_file.filename))
            
            try:
                uploaded_file.save(file_path)
            except Exception as e:
                logger.error(f"File save error: {e}")
                return jsonify({'error': 'Failed to save uploaded file'}), 500
            
            # Extract URLs
            if file_ext == '.txt':
                urls = extract_urls_from_txt(file_path)
            elif file_ext == '.pdf':
                urls = extract_urls_from_pdf(file_path)
            elif file_ext == '.docx':
                urls = extract_urls_from_docx(file_path)
        
        elif 'url' in request.form:
            url = request.form.get('url', '').strip()
            if validate_url(url):
                urls = [url]
        
        if not urls:
            return jsonify({'error': 'No valid URLs found'}), 400
        
        if len(urls) > MAX_URLS:
            return jsonify({'error': f'Too many URLs. Maximum: {MAX_URLS}'}), 400
        
        if not temp_dir:
            temp_dir = tempfile.mkdtemp()
        
        # Remove duplicates
        urls = list(dict.fromkeys(urls))
        
        logger.info(f"Processing {len(urls)} URL(s)")
        
        # PARALLEL DOWNLOADS (Increased from 3 to 5)
        downloaded = []
        failed = 0
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        max_parallel = min(5, len(urls))  # Increased to 5 parallel downloads
        
        with ThreadPoolExecutor(max_workers=max_parallel) as executor:
            future_to_url = {
                executor.submit(download_single_video, url, temp_dir, idx, quality): (idx, url)
                for idx, url in enumerate(urls)
            }
            
            for future in as_completed(future_to_url):
                idx, url = future_to_url[future]
                try:
                    result = future.result()
                    if result and result.get('success'):
                        downloaded.append(result['filename'])
                        dl_time = result.get('download_time', 0)
                        logger.info(f"[{idx+1}/{len(urls)}] ✓ {result.get('filesize_mb', 0):.1f}MB in {dl_time:.1f}s")
                    else:
                        failed += 1
                        logger.warning(f"[{idx+1}/{len(urls)}] ✗ Failed")
                except Exception as e:
                    failed += 1
                    logger.error(f"[{idx+1}/{len(urls)}] ✗ Error: {str(e)}")
        
        if not downloaded:
            return jsonify({'error': 'All downloads failed'}), 500
        
        logger.info(f"Completed: {len(downloaded)}/{len(urls)} (failed: {failed})")
        
        # Single video - send file
        if len(downloaded) == 1:
            video_file = downloaded[0]
            
            try:
                resp = send_file(
                    video_file,
                    as_attachment=True,
                    download_name=sanitize_filename(os.path.basename(video_file)),
                    mimetype='video/mp4'
                )
                resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                resp.headers['Pragma'] = 'no-cache'
                resp.headers['Expires'] = '0'
                
                import threading
                def delayed_cleanup():
                    time.sleep(10)
                    try:
                        if temp_dir and os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir)
                            logger.info(f"Cleaned up temp: {temp_dir}")
                    except Exception as e:
                        logger.error(f"Cleanup error: {e}")
                
                cleanup_thread = threading.Thread(target=delayed_cleanup, daemon=True)
                cleanup_thread.start()
                
                return resp
            except Exception as e:
                logger.error(f"Send file error: {e}")
                if temp_dir and os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir)
                    except:
                        pass
                return jsonify({'error': 'Failed to send file'}), 500
        
        # Multiple videos - create ZIP
        try:
            zip_path = os.path.join(temp_dir, 'videos.zip')
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for video_file in downloaded:
                    zf.write(video_file, sanitize_filename(os.path.basename(video_file)))
            
            resp = send_file(
                zip_path,
                as_attachment=True,
                download_name='videos.zip',
                mimetype='application/zip'
            )
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
            
            import threading
            def delayed_cleanup():
                time.sleep(10)
                try:
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                        logger.info(f"Cleaned up temp: {temp_dir}")
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")
            
            cleanup_thread = threading.Thread(target=delayed_cleanup, daemon=True)
            cleanup_thread.start()
            
            return resp
        except Exception as e:
            logger.error(f"ZIP creation error: {e}")
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
            return jsonify({'error': 'Failed to create ZIP'}), 500
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500
    
    finally:
        if temp_dir and 'Downloads' not in temp_dir:
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Cleanup error: {e}")