# watermarkimgvideo.py
import os
import io
import zipfile
import tempfile
import shutil
import traceback
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont
from pillow_heif import register_heif_opener
from moviepy.editor import VideoFileClip, ImageClip, TextClip, CompositeVideoClip
import numpy as np

# Register HEIF/HEIC support for PIL
register_heif_opener()

app = Flask(__name__)

# CORS configuration
CORS(app, resources={r"/*": {
    "origins": "*",
    "allow_headers": "*",
    "expose_headers": "*",
    "methods": ["GET", "POST", "OPTIONS"],
}}, supports_credentials=False)

app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

# Supported extensions
ALLOWED_IMAGE_EXT = {
    ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif",
    ".gif", ".bmp", ".tiff", ".tif"
}

ALLOWED_VIDEO_EXT = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"
}


def is_image_filename(name: str) -> bool:
    """Check if filename has a supported image extension."""
    _, ext = os.path.splitext(name.lower())
    return ext in ALLOWED_IMAGE_EXT


def is_video_filename(name: str) -> bool:
    """Check if filename has a supported video extension."""
    _, ext = os.path.splitext(name.lower())
    return ext in ALLOWED_VIDEO_EXT


def get_position_coords(position: str, container_width: int, container_height: int,
                       content_width: int, content_height: int, margin: int = 40):
    """Calculate x, y coordinates based on position string."""
    # Horizontal position
    if 'left' in position:
        x = margin
    elif 'center' in position:
        x = (container_width - content_width) // 2
    else:  # right
        x = container_width - content_width - margin

    # Vertical position
    if 'top' in position:
        y = margin
    elif 'middle' in position:
        y = (container_height - content_height) // 2
    else:  # lower/bottom
        y = container_height - content_height - margin

    return x, y



def add_text_watermark_to_image(image: Image.Image, text: str, font_size: int,
                                bold: bool, rotation: float, position: str,
                                transparency: int) -> Image.Image:
    """Add text watermark to an image."""
    # Convert to RGBA for transparency support
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    # Create a transparent overlay
    overlay = Image.new('RGBA', image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Try to load a font, fallback to default if not available
    try:
        # Try to use a system font
        if os.name == 'nt':  # Windows
            font_path = "C:\\Windows\\Fonts\\arial.ttf" if not bold else "C:\\Windows\\Fonts\\arialbd.ttf"
        else:  # Linux/Mac
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, font_size)
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    
    # Calculate text size using textbbox
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Create a separate image for rotated text
    text_image = Image.new('RGBA', (text_width + 100, text_height + 100), (255, 255, 255, 0))
    text_draw = ImageDraw.Draw(text_image)
    
    # Calculate opacity (transparency is percentage, we need alpha 0-255)
    opacity = int((transparency / 100) * 255)
    text_color = (0, 0, 0, opacity)
    
    # Draw text
    text_draw.text((50, 50), text, font=font, fill=text_color)
    
    # Rotate if needed
    if rotation != 0:
        text_image = text_image.rotate(rotation, expand=True)
    
    # Get final text image size after rotation
    # Remove transparent borders
    bbox = text_image.getbbox()
    if bbox:
        text_image = text_image.crop(bbox)
    
    # Calculate position
    x, y = get_position_coords(position, image.width, image.height,
                               text_image.width, text_image.height)
    
    # Paste text onto overlay
    overlay.paste(text_image, (x, y), text_image)
    
    # Composite the overlay onto the original image
    watermarked = Image.alpha_composite(image, overlay)
    
    return watermarked


def add_image_watermark_to_image(image: Image.Image, watermark_image: Image.Image,
                                 rotation: float, position: str, transparency: int) -> Image.Image:
    """Add image watermark to an image."""
    # Convert to RGBA for transparency support
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    # Convert watermark to RGBA
    if watermark_image.mode != 'RGBA':
        watermark_image = watermark_image.convert('RGBA')
    
    # Apply opacity to watermark
    opacity = transparency / 100
    if opacity < 1.0:
        alpha = watermark_image.split()[3]
        alpha = alpha.point(lambda p: int(p * opacity))
        watermark_image.putalpha(alpha)
    
    # Rotate watermark if needed
    if rotation != 0:
        watermark_image = watermark_image.rotate(rotation, expand=True)
    
    # Resize watermark to fit (max 40% of image width)
    max_width = int(image.width * 0.4)
    if watermark_image.width > max_width:
        ratio = max_width / watermark_image.width
        new_size = (int(watermark_image.width * ratio), int(watermark_image.height * ratio))
        watermark_image = watermark_image.resize(new_size, Image.Resampling.LANCZOS)
    
    # Calculate position
    x, y = get_position_coords(position, image.width, image.height,
                               watermark_image.width, watermark_image.height)
    
    # Create overlay and paste watermark
    overlay = Image.new('RGBA', image.size, (255, 255, 255, 0))
    overlay.paste(watermark_image, (x, y), watermark_image)
    
    # Composite
    watermarked = Image.alpha_composite(image, overlay)
    
    return watermarked


def add_watermark_to_video(video_path: str, output_path: str, watermark_type: str,
                           text: str = "", font_size: int = 48, rotation: float = 0,
                           position: str = "middle-center", transparency: int = 50,
                           watermark_image_path: str = None):
    """Add watermark to video using moviepy."""
    video = None
    txt_clip = None
    img_clip = None
    final_video = None
    
    try:
        # Load the video
        video = VideoFileClip(video_path)
        video_width, video_height = video.size
        
        # Calculate opacity (transparency is percentage, moviepy uses 0-1)
        opacity = transparency / 100
        
        if watermark_type == 'text':
            # Create text watermark using PIL (no ImageMagick required)
            # Create a transparent image for the text
            text_img = Image.new('RGBA', (video_width, video_height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(text_img)
            
            # Load font
            try:
                if os.name == 'nt':  # Windows
                    font_path = "C:\\Windows\\Fonts\\arial.ttf"
                else:  # Linux/Mac
                    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
                
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, font_size)
                else:
                    font = ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()
            
            # Calculate text size
            bbox = draw.textbbox((0, 0), text, font=font)
            txt_width = bbox[2] - bbox[0]
            txt_height = bbox[3] - bbox[1]
            
            # Create separate image for text with proper size
            text_layer = Image.new('RGBA', (txt_width + 100, txt_height + 100), (255, 255, 255, 0))
            text_draw = ImageDraw.Draw(text_layer)
            
            # Calculate text opacity
            text_opacity = int((transparency / 100) * 255)
            text_color = (0, 0, 0, text_opacity)
            
            # Draw text
            text_draw.text((50, 50), text, font=font, fill=text_color)
            
            # Rotate if needed
            if rotation != 0:
                text_layer = text_layer.rotate(rotation, expand=True)
            
            # Crop to content
            bbox = text_layer.getbbox()
            if bbox:
                text_layer = text_layer.crop(bbox)
            
            # Calculate position
            final_txt_width, final_txt_height = text_layer.size
            x, y = get_position_coords(position, video_width, video_height,
                                      final_txt_width, final_txt_height)
            
            # Convert PIL image to numpy array for moviepy
            text_array = np.array(text_layer)
            
            # Create ImageClip from the text array
            txt_clip = ImageClip(text_array).set_duration(video.duration)
            txt_clip = txt_clip.set_position((x, y))
            
            # Composite the text over the video
            final_video = CompositeVideoClip([video, txt_clip])
            
        elif watermark_type == 'image' and watermark_image_path:
            # Load watermark image using PIL first for better control
            with Image.open(watermark_image_path) as wm_img:
                # Convert to RGBA
                if wm_img.mode != 'RGBA':
                    wm_img = wm_img.convert('RGBA')
                
                # Resize if needed (max 40% of video width)
                max_width = int(video_width * 0.4)
                if wm_img.width > max_width:
                    ratio = max_width / wm_img.width
                    new_size = (int(wm_img.width * ratio), int(wm_img.height * ratio))
                    wm_img = wm_img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Rotate if needed
                if rotation != 0:
                    wm_img = wm_img.rotate(-rotation, expand=True)  # Negative for correct rotation
                
                # Convert PIL image to numpy array for moviepy
                wm_array = np.array(wm_img)
                
                # Create ImageClip from array
                img_clip = ImageClip(wm_array)
                
                # Set opacity
                img_clip = img_clip.set_opacity(opacity)
                
                # Calculate position
                img_width, img_height = img_clip.size
                x, y = get_position_coords(position, video_width, video_height,
                                          img_width, img_height)
                
                # Set position and duration
                img_clip = img_clip.set_position((x, y)).set_duration(video.duration)
                
                # Composite the image over the video
                final_video = CompositeVideoClip([video, img_clip])
        else:
            raise Exception("Invalid watermark configuration for video")
        
        # Create a temp directory for moviepy to use
        temp_dir = tempfile.mkdtemp(prefix="moviepy_temp_")
        
        try:
            # Write the result to file
            # Use codec based on output file extension
            ext = os.path.splitext(output_path)[1].lower()
            
            # Use threads=1 to avoid multi-threading issues on Windows
            write_params = {
                'codec': 'libx264',
                'audio_codec': 'aac',
                'temp_audiofile': os.path.join(temp_dir, 'temp_audio.m4a'),
                'remove_temp': True,
                'logger': None,
                'threads': 1  # Single thread to avoid file locking issues
            }
            
            if ext == '.mp4':
                final_video.write_videofile(output_path, **write_params)
            elif ext in ['.avi', '.mkv']:
                final_video.write_videofile(output_path, **write_params)
            elif ext == '.mov':
                final_video.write_videofile(output_path, **write_params)
            else:
                # Default codec
                final_video.write_videofile(
                    output_path,
                    temp_audiofile=os.path.join(temp_dir, 'temp_audio.m4a'),
                    remove_temp=True,
                    logger=None,
                    threads=1
                )
        finally:
            # Clean up temp directory
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
        
        return True
        
    except Exception as e:
        print(f"MoviePy error: {e}")
        traceback.print_exc()
        raise Exception(f"Video watermarking failed: {str(e)}")
    
    finally:
        # Ensure all clips are properly closed
        try:
            if final_video is not None:
                final_video.close()
        except Exception:
            pass
        
        try:
            if txt_clip is not None:
                txt_clip.close()
        except Exception:
            pass
        
        try:
            if img_clip is not None:
                img_clip.close()
        except Exception:
            pass
        
        try:
            if video is not None:
                video.close()
        except Exception:
            pass



def process_single_image(image_path: str, output_dir: str, watermark_type: str,
                        text: str, font_size: int, bold: bool, rotation: float,
                        position: str, transparency: int, watermark_image: Image.Image = None):
    """Process a single image file."""
    filename = os.path.basename(image_path)
    base_name = os.path.splitext(filename)[0]
    
    # Open image
    with Image.open(image_path) as img:
        # Add watermark based on type
        if watermark_type == 'text':
            result = add_text_watermark_to_image(img, text, font_size, bold,
                                                rotation, position, transparency)
        elif watermark_type == 'image' and watermark_image:
            result = add_image_watermark_to_image(img, watermark_image,
                                                 rotation, position, transparency)
        else:
            raise Exception("Invalid watermark configuration")
        
        # Save output - preserve format or convert to PNG if needed
        output_filename = f"{base_name}_watermarked.png"
        output_path = os.path.join(output_dir, output_filename)
        
        # Convert back to RGB if saving as JPG
        if filename.lower().endswith(('.jpg', '.jpeg')):
            output_filename = f"{base_name}_watermarked.jpg"
            output_path = os.path.join(output_dir, output_filename)
            if result.mode == 'RGBA':
                # Create white background
                background = Image.new('RGB', result.size, (255, 255, 255))
                background.paste(result, mask=result.split()[3] if result.mode == 'RGBA' else None)
                background.save(output_path, 'JPEG', quality=95)
            else:
                result.save(output_path, 'JPEG', quality=95)
        else:
            result.save(output_path, 'PNG')
        
        return output_path


def process_single_video(video_path: str, output_dir: str, watermark_type: str,
                        text: str, font_size: int, rotation: float,
                        position: str, transparency: int, watermark_image_path: str = None):
    """Process a single video file."""
    filename = os.path.basename(video_path)
    base_name = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1].lower()
    
    # Output with same extension
    output_filename = f"{base_name}_watermarked{ext}"
    output_path = os.path.join(output_dir, output_filename)
    
    # Add watermark to video
    add_watermark_to_video(video_path, output_path, watermark_type, text,
                          font_size, rotation, position, transparency,
                          watermark_image_path)
    
    return output_path


@app.get("/")
def index():
    return jsonify({"status": "ok", "note": "Watermark Image/Video API running"})


@app.post("/watermark-imgvideo")
def watermark_imgvideo_endpoint():
    """
    Endpoint to add watermarks to images and videos.
    - Single file upload: returns watermarked file
    - ZIP file upload: returns ZIP with all processed files
    """
    print("---- /watermark-imgvideo HIT ----")
    temp_root = None
    
    try:
        # Check file presence
        if "file" not in request.files:
            print("❌ ERROR: No file found in request")
            return jsonify({"error": "No file uploaded"}), 400

        uploaded = request.files["file"]
        filename = uploaded.filename or "uploaded"
        print("Uploaded filename:", filename)

        # Get watermark parameters
        watermark_type = request.form.get('type', 'text')
        text = request.form.get('text', 'SAMPLE')
        font_size = int(request.form.get('font_size', 48))
        bold = request.form.get('bold', 'false').lower() == 'true'
        rotation = float(request.form.get('rotation', 0))
        position = request.form.get('position', 'middle-center')
        transparency = int(request.form.get('transparency', 50))
        
        print(f"Watermark config: type={watermark_type}, text={text}, size={font_size}, pos={position}")

        # Handle watermark image if provided
        watermark_image = None
        watermark_image_path = None
        if watermark_type == 'image' and 'image_file' in request.files:
            img_file = request.files['image_file']
            if img_file.filename:
                watermark_image = Image.open(img_file.stream).convert('RGBA')
                print("Watermark image loaded:", img_file.filename)

        # Create temp directory
        temp_root = tempfile.mkdtemp(prefix="watermark_")
        print("Temp directory:", temp_root)

        input_dir = os.path.join(temp_root, "input")
        output_dir = os.path.join(temp_root, "output")
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        # Save watermark image to temp if needed for video processing
        if watermark_image:
            watermark_image_path = os.path.join(temp_root, "watermark.png")
            watermark_image.save(watermark_image_path, 'PNG')

        # Save uploaded file
        uploaded_path = os.path.join(temp_root, filename)
        uploaded.save(uploaded_path)
        print("Saved uploaded file at:", uploaded_path)

        processed_files = []
        is_zip_upload = False

        # Check if uploaded file is a ZIP
        if filename.lower().endswith(".zip"):
            is_zip_upload = True
            print("Processing ZIP file...")
            
            try:
                with zipfile.ZipFile(uploaded_path, "r") as ztest:
                    test = ztest.testzip()
                    if test is not None:
                        return jsonify({"error": "ZIP file appears corrupted"}), 400
            except zipfile.BadZipFile:
                return jsonify({"error": "Uploaded file is not a valid ZIP file"}), 400

            # Extract ZIP
            with zipfile.ZipFile(uploaded_path, "r") as z:
                print("ZIP entries:", z.namelist())
                z.extractall(input_dir)

            # Process all files in ZIP
            for root, dirs, files in os.walk(input_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    
                    try:
                        if is_image_filename(fname):
                            print(f"Processing image: {fname}")
                            output_path = process_single_image(
                                fpath, output_dir, watermark_type, text,
                                font_size, bold, rotation, position,
                                transparency, watermark_image
                            )
                            processed_files.append(output_path)
                            
                        elif is_video_filename(fname):
                            print(f"Processing video: {fname}")
                            output_path = process_single_video(
                                fpath, output_dir, watermark_type, text,
                                font_size, rotation, position,
                                transparency, watermark_image_path
                            )
                            processed_files.append(output_path)
                        else:
                            print(f"Skipping unsupported file: {fname}")
                            
                    except Exception as e:
                        print(f"❌ ERROR processing {fname}: {e}")
                        traceback.print_exc()
                        return jsonify({"error": f"Failed to process '{fname}': {str(e)}"}), 500

        # Single file upload
        elif is_image_filename(filename):
            print("Processing single image...")
            try:
                output_path = process_single_image(
                    uploaded_path, output_dir, watermark_type, text,
                    font_size, bold, rotation, position,
                    transparency, watermark_image
                )
                processed_files.append(output_path)
            except Exception as e:
                print(f"❌ IMAGE ERROR: {e}")
                traceback.print_exc()
                return jsonify({"error": f"Failed to process image: {str(e)}"}), 500

        elif is_video_filename(filename):
            print("Processing single video...")
            try:
                output_path = process_single_video(
                    uploaded_path, output_dir, watermark_type, text,
                    font_size, rotation, position,
                    transparency, watermark_image_path
                )
                processed_files.append(output_path)
            except Exception as e:
                print(f"❌ VIDEO ERROR: {e}")
                traceback.print_exc()
                return jsonify({"error": f"Failed to process video: {str(e)}"}), 500

        else:
            return jsonify({"error": "Unsupported file type. Please upload images, videos, or a ZIP file."}), 400

        # Check if any files were processed
        if not processed_files:
            return jsonify({"error": "No valid files were processed."}), 400

        # Return results
        if len(processed_files) == 1 and not is_zip_upload:
            # Single file processed
            output_file = processed_files[0]
            print(f"Returning single file: {os.path.basename(output_file)}")
            
            response = send_file(
                output_file,
                as_attachment=True,
                download_name=os.path.basename(output_file)
            )
        else:
            # Multiple files or ZIP input - return ZIP
            print("Creating output ZIP...")
            output_zip_path = os.path.join(temp_root, "watermarked_files.zip")
            
            with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for out_file in processed_files:
                    zout.write(out_file, arcname=os.path.basename(out_file))
            
            print(f"Output ZIP ready: {output_zip_path}")
            
            download_name = "watermarked_files.zip"
            if filename.lower().endswith(".zip"):
                base = os.path.splitext(filename)[0]
                download_name = f"{base}_watermarked.zip"
            
            response = send_file(
                output_zip_path,
                as_attachment=True,
                download_name=download_name,
                mimetype="application/zip"
            )

        # Cleanup after response
        def cleanup():
            try:
                print(f"Cleaning temp: {temp_root}")
                shutil.rmtree(temp_root)
            except Exception as e:
                print(f"Cleanup failed: {e}")
        
        response.call_on_close(cleanup)
        return response

    except Exception as e:
        print("\n❌ GLOBAL ERROR:", e)
        traceback.print_exc()
        
        # Cleanup on error
        try:
            if temp_root and os.path.exists(temp_root):
                shutil.rmtree(temp_root)
        except Exception:
            pass
        
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)