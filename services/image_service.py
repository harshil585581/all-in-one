# Image processing service - Business logic for image operations
import io
import os
import zipfile
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

# Try to enable HEIC/HEIF support via pillow-heif (optional).
HEIC_AVAILABLE = False
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_AVAILABLE = True
except Exception:
    HEIC_AVAILABLE = False

# Supported image extensions (lowercase)
ALLOWED_IMAGE_EXTS = {
    '.png', '.webp', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.tif', '.heic', '.heif'
}
ALLOWED_INPUT_EXTS = ALLOWED_IMAGE_EXTS.union({'.zip'})


def ext_of_filename(name: str) -> str:
    """Extract file extension in lowercase."""
    return os.path.splitext(name)[1].lower()


def is_image_ext(ext: str) -> bool:
    """Check if extension is a supported image format."""
    return ext in ALLOWED_IMAGE_EXTS


def compress_image_bytes(file_bytes: bytes, original_ext: str, quality: int = 85) -> tuple:
    """
    Compress image bytes while preserving the original format.
    Returns (compressed_bytes, mimetype, out_ext).
    Applies quality-based compression for all formats.
    Quality: 10-95, lower = smaller file size but lower visual quality.
    """
    with Image.open(io.BytesIO(file_bytes)) as im:
        # For animated GIFs, take the first frame
        if getattr(im, "is_animated", False):
            try:
                im.seek(0)
                im = im.copy()
            except Exception:
                pass

        out_buf = io.BytesIO()
        
        # Determine output format based on original extension
        if original_ext in ['.png']:
            # PNG: Apply quality through color quantization for smaller files
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                if im.mode == "P":
                    im = im.convert("RGBA")
                if quality < 95:
                    max_colors = int(16 + (quality / 95.0) * 240)
                    im = im.quantize(colors=max_colors, method=2).convert("RGBA")
                im.save(out_buf, format="PNG", optimize=True, compress_level=9)
            else:
                rgb_im = im.convert("RGB")
                if quality < 95:
                    max_colors = int(16 + (quality / 95.0) * 240)
                    rgb_im = rgb_im.quantize(colors=max_colors, method=2).convert("RGB")
                rgb_im.save(out_buf, format="PNG", optimize=True, compress_level=9)
            mimetype = "image/png"
            out_ext = ".png"
            
        elif original_ext in ['.webp']:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                if im.mode == "P":
                    im = im.convert("RGBA")
                im.save(out_buf, format="WEBP", quality=quality, method=6, lossless=False)
            else:
                rgb_im = im.convert("RGB")
                rgb_im.save(out_buf, format="WEBP", quality=quality, method=6, lossless=False)
            mimetype = "image/webp"
            out_ext = ".webp"
            
        elif original_ext in ['.jpg', '.jpeg']:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                try:
                    bg.paste(im, mask=im.split()[-1])
                except Exception:
                    bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                out_im = bg
            else:
                out_im = im.convert("RGB")
            out_im.save(out_buf, format="JPEG", quality=quality, optimize=True, subsampling=0 if quality >= 90 else 2)
            mimetype = "image/jpeg"
            out_ext = ".jpg"
            
        elif original_ext in ['.bmp']:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                try:
                    bg.paste(im, mask=im.split()[-1])
                except Exception:
                    bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                out_im = bg
            else:
                out_im = im.convert("RGB")
            out_im.save(out_buf, format="JPEG", quality=quality, optimize=True)
            mimetype = "image/jpeg"
            out_ext = ".jpg"
            
        elif original_ext in ['.gif']:
            if quality < 95:
                max_colors = int(8 + (quality / 95.0) * 248)
                if im.mode != "P":
                    im = im.convert("RGB").quantize(colors=max_colors, method=2)
                else:
                    im = im.convert("RGB").quantize(colors=max_colors, method=2)
            im.save(out_buf, format="GIF", optimize=True, save_all=False)
            mimetype = "image/gif"
            out_ext = ".gif"
            
        elif original_ext in ['.tiff', '.tif']:
            if im.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                try:
                    bg.paste(im, mask=im.split()[-1])
                except Exception:
                    bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                out_im = bg
            else:
                out_im = im.convert("RGB")
            out_im.save(out_buf, format="JPEG", quality=quality, optimize=True)
            mimetype = "image/jpeg"
            out_ext = ".jpg"
            
        elif original_ext in ['.heic', '.heif']:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                try:
                    bg.paste(im, mask=im.split()[-1])
                except Exception:
                    bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                out_im = bg
            else:
                out_im = im.convert("RGB")
            out_im.save(out_buf, format="JPEG", quality=quality, optimize=True)
            mimetype = "image/jpeg"
            out_ext = ".jpg"
        else:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                try:
                    bg.paste(im, mask=im.split()[-1])
                except Exception:
                    bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
                out_im = bg
            else:
                out_im = im.convert("RGB")
            out_im.save(out_buf, format="JPEG", quality=quality, optimize=True)
            mimetype = "image/jpeg"
            out_ext = ".jpg"

        out_buf.seek(0)
        return out_buf.read(), mimetype, out_ext
