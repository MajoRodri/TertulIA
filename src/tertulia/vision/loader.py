"""Open the photos for the vision agent safely, ready to send to the model.

The paths come from BusinessBrief.image_paths, which already refuses "..",
absolute paths and non-image extensions (first check, on the text). Here is
the second check, on the real file, because a name can lie:

1. The REAL path is resolved (symbolic links included) and must still be
   inside outputs/: "photo.jpg" could be a link to a file elsewhere.
2. At most 10 MB, and its content must really be a JPEG or PNG image,
   whatever its extension says.
3. It is reduced to 1,600 px on its longest side (faster and cheaper; a menu
   is still readable) and saved again, which also drops its metadata (EXIF),
   such as the GPS position where the photo was taken.
"""

import base64
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

# loader.py lives in <repo>/src/tertulia/vision/
OUTPUTS_DIR = Path(__file__).resolve().parents[3] / "outputs"
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_SIDE_PX = 1600
# Pillow format name -> MIME type the model expects
ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png"}


class ImageRejected(ValueError):
    """The file cannot be analysed. The message says why, for the analyst."""


@dataclass(frozen=True)
class LoadedImage:
    """A checked photo, ready to go inside a message to the model."""

    image_path: str  # as given, relative to outputs/
    mime_type: str
    data_b64: str  # the reduced image, as text (base64)
    width: int
    height: int


def _real_path(image_path: str, root: Path) -> Path:
    """Resolve the real file (following links) and check it stays inside root."""
    real_root = root.resolve()
    real_file = (real_root / image_path).resolve()
    if not real_file.is_relative_to(real_root):
        raise ImageRejected(f"{image_path!r} points outside the allowed folder")
    if not real_file.is_file():
        raise ImageRejected(f"{image_path!r} does not exist")
    return real_file


def load_image(image_path: str, root: Path = OUTPUTS_DIR) -> LoadedImage:
    """Check one photo and return it reduced and encoded for the model."""
    real_file = _real_path(image_path, root)
    if real_file.stat().st_size > MAX_FILE_BYTES:
        raise ImageRejected(f"{image_path!r} is larger than {MAX_FILE_BYTES // 2**20} MB")

    try:
        with Image.open(real_file) as image:
            image_format = image.format
            image.verify()  # reads the whole file: a broken or fake image fails here
        if image_format not in ALLOWED_FORMATS:
            raise ImageRejected(f"{image_path!r} is not a JPEG or PNG image")
        # verify() leaves the image unusable, so it is opened again.
        with Image.open(real_file) as image:
            image = ImageOps.exif_transpose(image)  # mobile photos: keep them upright
            image.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))  # only ever makes it smaller
            if image_format == "JPEG" and image.mode != "RGB":
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format=image_format)  # no exif= argument: metadata dropped
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as error:
        raise ImageRejected(f"{image_path!r} is not a valid image") from error

    return LoadedImage(
        image_path=image_path,
        mime_type=ALLOWED_FORMATS[image_format],
        data_b64=base64.b64encode(buffer.getvalue()).decode("ascii"),
        width=image.width,
        height=image.height,
    )