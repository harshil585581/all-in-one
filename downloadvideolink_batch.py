# downloadvideolink_batch.py
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import shutil
import zipfile
from pathlib import Path
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import PyPDF2
from docx import Document

app = Flask(__name__)

# Configure CORS with proper OPTIONS support
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:4200", "http://127.0.0.1:4200"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"],
        "expose_headers": ["Content-Disposition"],
        "supports_credentials": False
    }
})

def extract_urls_from_text(text):
    """Extract all URLs from text using regex"""
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    urls = re.findall(url_pattern, text)
    return [url.strip() for url in urls if url.strip()]

def extract_urls_from_txt(file_path):
    """Extract URLs from .txt file"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    return extract_urls_from_text(content)

def extract_urls_from_pdf(file_path):
    """Extract URLs from .pdf file"""
    urls = []
    try:
        with open(file_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            for page in pdf_reader.pages:
                text = page.extract_text()
                urls.extend(extract_urls_from_text(text))
    except Exception as e:
        print(f"PDF extraction error: {e}")
    return urls

def extract_urls_from_docx(file_path):
    """Extract URLs from .docx file"""
    urls = []
    try:
        doc = Document(file_path)
        for para in doc.paragraphs:
            urls.extend(extract_urls_from_text(para.text))
    except Exception as e:
        print(f"DOCX extraction error: {e}")
    return urls

def download_single_video(url, output_dir, index=0):
    """Download a single video and return the file path"""
    try:
        output_template = os.path.join(output_dir, f'video_{index}.%(ext)s')
        
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'merge_output_format': 'mp4',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            },
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return None
            
            filename = ydl.prepare_filename(info)
            if os.path.exists(filename):
                # Get video title for better naming
                title = info.get('title', f'video_{index}')
                safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_title = safe_title[:50]
                
                ext = os.path.splitext(filename)[1]
                new_filename = os.path.join(output_dir, f'{safe_title}{ext}')
                
                # Handle duplicate names
                counter = 1
                base_new_filename = new_filename
                while os.path.exists(new_filename):
                    name_without_ext = os.path.splitext(base_new_filename)[0]
                    new_filename = f"{name_without_ext}_{counter}{ext}"
                    counter += 1
                
                # Rename if needed
                if filename != new_filename:
                    shutil.move(filename, new_filename)
                    filename = new_filename
                
                return {
                    'success': True,
                    'url': url,
                    'filename': filename,
                    'title': safe_title
                }
            
        return None
        
    except Exception as e:
        print(f"❌ Download error for {url}: {str(e)}")
        return {
            'success': False,
            'url': url,
            'error': str(e)
        }

@app.route('/download-video-batch', methods=['POST'])
def download_video_batch():
    """Handle batch video downloads from URL or file with links"""
    temp_dir = None
    
    try:
        urls = []
        
        # Check if file was uploaded
        if 'file' in request.files:
            uploaded_file = request.files['file']
            if uploaded_file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            # Save uploaded file temporarily
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, uploaded_file.filename)
            uploaded_file.save(file_path)
            
            print(f"📄 Processing file: {uploaded_file.filename}")
            
            # Extract URLs based on file type
            filename_lower = uploaded_file.filename.lower()
            if filename_lower.endswith('.txt'):
                urls = extract_urls_from_txt(file_path)
            elif filename_lower.endswith('.pdf'):
                urls = extract_urls_from_pdf(file_path)
            elif filename_lower.endswith('.docx'):
                urls = extract_urls_from_docx(file_path)
            else:
                return jsonify({'error': 'Unsupported file type. Please use .txt, .pdf, or .docx'}), 400
            
            if not urls:
                return jsonify({'error': 'No valid URLs found in file'}), 400
                
        # Check if single URL was provided
        elif 'url' in request.form:
            url = request.form.get('url')
            if not url:
                return jsonify({'error': 'No URL provided'}), 400
            urls = [url]
        else:
            return jsonify({'error': 'No URL or file provided'}), 400
        
        # Create temp directory if not created
        if not temp_dir:
            temp_dir = tempfile.mkdtemp()
        
        # Remove duplicates while preserving order
        urls = list(dict.fromkeys(urls))
        
        print(f"📥 Processing {len(urls)} URL(s)")
        
        # Download videos
        downloaded_files = []
        failed_urls = []
        
        for idx, url in enumerate(urls):
            print(f"🔄 Downloading {idx + 1}/{len(urls)}: {url[:60]}...")
            result = download_single_video(url, temp_dir, idx)
            if result and result.get('success'):
                downloaded_files.append(result['filename'])
                print(f"   ✅ Success: {result.get('title', 'video')}")
            else:
                failed_urls.append(url)
                error_msg = result.get('error', 'Unknown error') if result else 'Download failed'
                print(f"   ❌ Failed: {error_msg[:60]}")
        
        if not downloaded_files:
            error_msg = 'All downloads failed'
            if failed_urls:
                error_msg += f'. Failed URLs: {len(failed_urls)}'
            return jsonify({'error': error_msg}), 500
        
        print(f"✅ Successfully downloaded {len(downloaded_files)}/{len(urls)} video(s)")
        
        # Single video - return directly
        if len(downloaded_files) == 1:
            video_file = downloaded_files[0]
            filename = os.path.basename(video_file)
            
            print(f"📤 Sending single video: {filename}")
            
            response = send_file(
                video_file,
                as_attachment=True,
                download_name=filename,
                mimetype='video/mp4'
            )
            
            # Add CORS headers
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
            response.headers['Cache-Control'] = 'no-cache'
            
            # Cleanup after sending
            @response.call_on_close
            def cleanup():
                try:
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                        print(f"🧹 Cleaned up temp directory")
                except Exception as e:
                    print(f"⚠️ Cleanup error: {str(e)}")
            
            return response
        
        # Multiple videos - create ZIP
        zip_path = os.path.join(temp_dir, 'videos.zip')
        
        print(f"📦 Creating ZIP with {len(downloaded_files)} videos...")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for video_file in downloaded_files:
                arcname = os.path.basename(video_file)
                zipf.write(video_file, arcname)
                print(f"   ➕ Added: {arcname}")
        
        print(f"✅ ZIP created successfully")
        
        response = send_file(
            zip_path,
            as_attachment=True,
            download_name='videos.zip',
            mimetype='application/zip'
        )
        
        # Add CORS headers
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
        response.headers['Cache-Control'] = 'no-cache'
        
        # Cleanup after sending
        @response.call_on_close
        def cleanup():
            try:
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    print(f"🧹 Cleaned up temp directory")
            except Exception as e:
                print(f"⚠️ Cleanup error: {str(e)}")
        
        return response
        
    except Exception as e:
        print(f"❌ General error: {str(e)}")
        
        # Cleanup on error
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
                
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'service': 'batch-video-download',
        'features': ['single-url', 'batch-url', 'file-upload'],
        'supported_files': ['.txt', '.pdf', '.docx']
    }), 200

if __name__ == '__main__':
    print("🎥 Batch Video Download Service Starting...")
    print("📍 Endpoint: http://127.0.0.1:5000/download-video-batch")
    print("✨ Features: Single URL, Batch URLs, File Upload (.txt, .docx, .pdf)")
    print("🌐 Supported: YouTube, Vimeo, TikTok, Instagram, and 1000+ sites")
    app.run(debug=True, port=5000, host='127.0.0.1')
