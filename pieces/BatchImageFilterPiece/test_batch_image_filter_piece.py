import base64
import sys
from io import BytesIO
from pathlib import Path

import pytest
from domino.schemas.deploy_mode import DeployModeType
from PIL import Image
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pieces.BatchImageFilterPiece.models import InputModel
from pieces.BatchImageFilterPiece.piece import BatchImageFilterPiece


def test_rejects_invalid_max_concurrency():
    with pytest.raises(ValidationError):
        InputModel(max_concurrency=0)


def test_preserves_one_output_slot_per_input(tmp_path):
    image = Image.new("RGB", (4, 4), color=(100, 150, 200))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded_image = base64.b64encode(buffer.getvalue()).decode("utf-8")

    piece = BatchImageFilterPiece(DeployModeType.dry_run, "test_task", "test_dag")
    piece.results_path = str(tmp_path)

    output = piece.piece_function(
        InputModel(
            input_images=[encoded_image, None],
            black_and_white=True,
            output_type="both",
            max_concurrency=8,
        )
    )

    assert output.input_count == 2
    assert output.successful_count == 1
    assert output.failed_count == 1
    assert len(output.image_base64_strings) == 2
    assert len(output.image_file_paths) == 2
    assert output.image_base64_strings[0] is not None
    assert output.image_file_paths[0] is not None
    assert output.image_base64_strings[1] is None
    assert output.image_file_paths[1] is None
    assert piece.display_result["file_type"] == "html"
    assert Path(piece.display_result["file_path"]).exists()
    assert "Filtered image 0" in Path(piece.display_result["file_path"]).read_text()


def test_processes_multiple_valid_images(tmp_path):
    encoded_images = []
    for color in [(100, 150, 200), (200, 150, 100), (50, 75, 125)]:
        image = Image.new("RGB", (4, 4), color=color)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded_images.append(base64.b64encode(buffer.getvalue()).decode("utf-8"))

    piece = BatchImageFilterPiece(DeployModeType.dry_run, "test_task", "test_dag")
    piece.results_path = str(tmp_path)

    output = piece.piece_function(
        InputModel(
            input_images=encoded_images,
            sepia=True,
            output_type="both",
            max_concurrency=8,
        )
    )

    assert output.input_count == 3
    assert output.successful_count == 3
    assert output.failed_count == 0
    assert len(output.image_base64_strings) == 3
    assert len(output.image_file_paths) == 3
    assert all(image_base64_string is not None for image_base64_string in output.image_base64_strings)
    assert all(Path(image_file_path).exists() for image_file_path in output.image_file_paths)
    display_html = Path(piece.display_result["file_path"]).read_text()
    assert "Filtered image 0" in display_html
    assert "Filtered image 1" in display_html
    assert "Filtered image 2" in display_html
