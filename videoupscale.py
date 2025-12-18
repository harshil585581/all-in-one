from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os
import io
import zipfile
import tempfile
import shutil
import subprocess
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
CORS(app)

# FFmpeg installation path
FFMPEG_PATH = r"C:\Users\HARSHIL\AppData\Local\Programs\ffmpeg\bin"
FFMPEG_EXE = os.path.join(FFMPEG_PATH, "ffmpeg.exe")
FFPROBE_EXE = os.path.join(FFMPEG_PATH, "ffprobe.exe")

# Supported video extensions
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.flv', '.wmv', '.mpg', '.mpeg', '.m4v', '.3gp'}

def get_video_dimensions(video_path):
    """Get video dimensions using ffprobe"""
    try:
        # Check if file exists
        if not os.path.exists(video_path):
            raise Exception(f"Video file not found: {video_path}")
        
        # Check file size
        file_size = os.path.getsize(video_path)
        if file_size == 0:
            raise Exception(f"Video file is empty (0 bytes)")
        
        print(f"Checking video dimensions for: {video_path} (size: {file_size} bytes)")
        
        cmd = [
            FFPROBE_EXE, '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=p=0',
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Check if we got output
        output = result.stdout.strip()
        if not output:
            raise Exception(f"ffprobe returned empty output. stderr: {result.stderr}")
        
        print(f"ffprobe output: {output}")
        
        # Parse dimensions
        if ',' not in output:
            raise Exception(f"Unexpected ffprobe output format: {output}")
        
        width, height = map(int, output.split(','))
        
        if width <= 0 or height <= 0:
            raise Exception(f"Invalid video dimensions: {width}x{height}")
        
        print(f"Video dimensions: {width}x{height}")
        return width, height
        
    except subprocess.CalledProcessError as e:
        error_msg = f"ffprobe command failed. Return code: {e.returncode}, stderr: {e.stderr}, stdout: {e.stdout}"
        print(f"Error getting video dimensions: {error_msg}")
        raise Exception(error_msg)
    except FileNotFoundError:
        error_msg = "ffprobe not found. Please ensure FFmpeg is installed and in PATH"
        print(f"Error getting video dimensions: {error_msg}")
        raise Exception(error_msg)
    except ValueError as e:
        error_msg = f"Failed to parse video dimensions: {e}"
        print(f"Error getting video dimensions: {error_msg}")
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"Error getting video dimensions: {error_msg}")
        raise Exception(error_msg)

def calculate_scale_filter(scale_param, original_width, original_height):
    """Calculate ffmpeg scale filter based on scale parameter"""
    if scale_param == '2x':
        return f'scale={original_width*2}:{original_height*2}'
    elif scale_param == '4x':
        return f'scale={original_width*4}:{original_height*4}'
    elif ':' in scale_param:
        # Direct resolution like 1920:1080 or 3840:2160
        target_width, target_height = scale_param.split(':')
        return f'scale={target_width}:{target_height}'
    else:
        # Default to 2x if unknown
        return f'scale={original_width*2}:{original_height*2}'

def upscale_video(input_path, output_path, scale, crf):
    """Upscale a single video using ffmpeg"""
    try:
        # Get original dimensions (will raise exception if fails)
        width, height = get_video_dimensions(input_path)
        
        # Calculate scale filter
        scale_filter = calculate_scale_filter(scale, width, height)
        
        # ffmpeg command for upscaling
        cmd = [
            FFMPEG_EXE, '-i', input_path,
            '-vf', scale_filter,
            '-c:v', 'libx264',
            '-crf', str(crf),
            '-preset', 'medium',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-y',  # Overwrite output file
            output_path
        ]
        
        print(f"Running ffmpeg command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"Video upscaled successfully: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error: {e.stderr}")
        raise Exception(f"FFmpeg processing failed: {e.stderr}")
    except Exception as e:
        print(f"Error upscaling video: {e}")
        raise

def process_single_video(video_file, scale, crf):
    """Process a single video file"""
    temp_dir = tempfile.mkdtemp()
    try:
        # Save uploaded file
        original_filename = secure_filename(video_file.filename)
        input_path = os.path.join(temp_dir, original_filename)
        video_file.save(input_path)
        
        # Create output filename
        name_without_ext = os.path.splitext(original_filename)[0]
        output_filename = f"{name_without_ext}_upscaled.mp4"
        output_path = os.path.join(temp_dir, output_filename)
        
        # Upscale video
        upscale_video(input_path, output_path, scale, crf)
        
        # Read output file to memory
        with open(output_path, 'rb') as f:
            output_data = io.BytesIO(f.read())
        
        output_data.seek(0)
        return output_data, output_filename
    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Error cleaning up temp dir: {e}")

def process_zip_videos(zip_file, scale, crf):
    """Process multiple videos from a ZIP file"""
    temp_dir = tempfile.mkdtemp()
    output_dir = tempfile.mkdtemp()
    
    try:
        # Save uploaded ZIP
        zip_path = os.path.join(temp_dir, 'input.zip')
        zip_file.save(zip_path)
        
        # Extract ZIP
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # Find all video files
        video_files = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in VIDEO_EXTENSIONS:
                    video_files.append(os.path.join(root, file))
        
        if not video_files:
            raise Exception("No video files found in ZIP")
        
        print(f"Found {len(video_files)} video(s) to process")
        
        # Process each video
        processed_files = []
        for i, video_path in enumerate(video_files):
            try:
                original_name = os.path.basename(video_path)
                name_without_ext = os.path.splitext(original_name)[0]
                output_filename = f"{name_without_ext}_upscaled.mp4"
                output_path = os.path.join(output_dir, output_filename)
                
                print(f"Processing video {i+1}/{len(video_files)}: {original_name}")
                upscale_video(video_path, output_path, scale, crf)
                processed_files.append(output_path)
            except Exception as e:
                print(f"Error processing {video_path}: {e}")
                # Continue processing other videos
        
        if not processed_files:
            raise Exception("Failed to process any videos")
        
        # Create output ZIP
        output_zip_path = os.path.join(temp_dir, 'output.zip')
        with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_out:
            for file_path in processed_files:
                zip_out.write(file_path, os.path.basename(file_path))
        
        # Read output ZIP to memory
        with open(output_zip_path, 'rb') as f:
            output_data = io.BytesIO(f.read())
        
        output_data.seek(0)
        
        # Generate output filename
        original_zip_name = secure_filename(zip_file.filename)
        name_without_ext = os.path.splitext(original_zip_name)[0]
        output_filename = f"{name_without_ext}_upscaled.zip"
        
        return output_data, output_filename
    finally:
        # Cleanup temp directories
        try:
            shutil.rmtree(temp_dir)
            shutil.rmtree(output_dir)
        except Exception as e:
            print(f"Error cleaning up temp dirs: {e}")

@app.route('/video-upscale', methods=['POST', 'OPTIONS'])
def video_upscale():
    # Handle OPTIONS preflight request
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    
    try:
        # Validate file upload
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get parameters
        scale = request.form.get('scale', '2x')
        crf = int(request.form.get('crf', 18))
        
        # Validate CRF
        if crf < 0 or crf > 51:
            return jsonify({'error': 'CRF must be between 0 and 51'}), 400
        
        # Check if it's a ZIP file
        filename = secure_filename(file.filename)
        is_zip = filename.lower().endswith('.zip')
        
        if is_zip:
            # Process multiple videos from ZIP
            print(f"Processing ZIP file: {filename}")
            output_data, output_filename = process_zip_videos(file, scale, crf)
            mimetype = 'application/zip'
        else:
            # Process single video
            print(f"Processing single video: {filename}")
            output_data, output_filename = process_single_video(file, scale, crf)
            mimetype = 'video/mp4'
        
        # Send file
        return send_file(
            output_data,
            mimetype=mimetype,
            as_attachment=True,
            download_name=output_filename
        )
    
    except Exception as e:
        print(f"Error in video-upscale endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'video-upscale'}), 200

if __name__ == '__main__':
    # Check if ffmpeg is available
    try:
        subprocess.run([FFMPEG_EXE, '-version'], capture_output=True, check=True)
        subprocess.run([FFPROBE_EXE, '-version'], capture_output=True, check=True)
        print(f"FFmpeg and FFprobe are available at: {FFMPEG_PATH}")
    except Exception as e:
        print(f"WARNING: FFmpeg or FFprobe not found at: {FFMPEG_PATH}")
        print(f"Error: {e}")
    
    print("Starting Video Upscale API on http://127.0.0.1:5000")
    app.run(debug=True, host='127.0.0.1', port=5000)
