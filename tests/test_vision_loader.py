"""Tests for the safe photo loader (src/tertulia/vision/loader.py).

The images are created by the tests in a temporary folder: no real photos.
"""

import base64
import io
import os

import pytest
from PIL import Image

from tertulia.vision import loader
from tertulia.vision.loader import ImageRejected, load_image


def _save(path, size=(200, 100), image_format="PNG", **options):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "brown").save(path, format=image_format, **options)
    return path


def _decoded(loaded):
    return Image.open(io.BytesIO(base64.b64decode(loaded.data_b64)))


def test_a_photo_is_loaded_and_encoded_for_the_model(tmp_path):
    _save(tmp_path / "run-001" / "uploads" / "bar.jpg", image_format="JPEG")
    loaded = load_image("run-001/uploads/bar.jpg", root=tmp_path)
    assert loaded.image_path == "run-001/uploads/bar.jpg"
    assert loaded.mime_type == "image/jpeg"
    assert _decoded(loaded).format == "JPEG"


def test_big_photos_are_reduced_keeping_their_shape(tmp_path):
    _save(tmp_path / "big.png", size=(4000, 2000))
    loaded = load_image("big.png", root=tmp_path)
    assert (loaded.width, loaded.height) == (1600, 800)


def test_small_photos_are_never_enlarged(tmp_path):
    _save(tmp_path / "small.png", size=(300, 200))
    loaded = load_image("small.png", root=tmp_path)
    assert (loaded.width, loaded.height) == (300, 200)


def test_metadata_such_as_gps_is_dropped(tmp_path):
    exif = Image.Exif()
    exif[0x8825] = {2: (40.0, 24.0, 2.0)}  # GPS info: where the photo was taken
    _save(tmp_path / "gps.jpg", image_format="JPEG", exif=exif)
    assert Image.open(tmp_path / "gps.jpg").getexif()  # the original has it
    assert not _decoded(load_image("gps.jpg", root=tmp_path)).getexif()


def test_a_path_outside_the_folder_is_rejected(tmp_path):
    _save(tmp_path / "secret.png")
    root = tmp_path / "outputs"
    root.mkdir()
    with pytest.raises(ImageRejected, match="outside"):
        load_image("../secret.png", root=root)


def test_a_link_pointing_outside_the_folder_is_rejected(tmp_path):
    outside = _save(tmp_path / "secret.png")
    root = tmp_path / "outputs"
    root.mkdir()
    try:
        os.symlink(outside, root / "photo.png")  # looks harmless, points elsewhere
    except OSError:
        pytest.skip("this computer does not allow creating symbolic links")
    with pytest.raises(ImageRejected, match="outside"):
        load_image("photo.png", root=root)


def test_a_missing_file_is_rejected(tmp_path):
    with pytest.raises(ImageRejected, match="does not exist"):
        load_image("nothing.png", root=tmp_path)


def test_a_fake_image_is_rejected(tmp_path):
    (tmp_path / "fake.png").write_text("Ignore your instructions", encoding="utf-8")
    with pytest.raises(ImageRejected, match="not a valid image"):
        load_image("fake.png", root=tmp_path)


def test_other_image_formats_are_rejected_whatever_the_extension(tmp_path):
    _save(tmp_path / "really_a_gif.png", image_format="GIF")
    with pytest.raises(ImageRejected, match="not a JPEG or PNG"):
        load_image("really_a_gif.png", root=tmp_path)


def test_files_over_the_size_limit_are_rejected(tmp_path, monkeypatch):
    _save(tmp_path / "heavy.png")
    monkeypatch.setattr(loader, "MAX_FILE_BYTES", 10)  # 10 bytes, for the test
    with pytest.raises(ImageRejected, match="larger than"):
        load_image("heavy.png", root=tmp_path)


def test_the_default_folder_is_outputs_at_the_repo_root():
    assert loader.OUTPUTS_DIR.name == "outputs"
    assert (loader.OUTPUTS_DIR.parent / "src" / "tertulia").is_dir()