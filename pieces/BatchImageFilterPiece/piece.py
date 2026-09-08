import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from domino.base_piece import BasePiece
from PIL import Image, ImageEnhance, ImageOps

from .models import InputModel, OutputModel, OutputTypeEnum


class BatchImageFilterPiece(BasePiece):

    def piece_function(self, input_data: InputModel):
        if not input_data.input_images:
            raise ValueError("At least one input image must be provided.")

        input_count = len(input_data.input_images)
        max_workers = min(input_data.max_concurrency, input_count)
        self.logger.info(f"Filtering {input_count} images with up to {max_workers} concurrent workers.")

        image_base64_strings = [None] * input_count
        image_file_paths = [None] * input_count

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(self._process_image, index, image_input, input_data): index
                for index, image_input in enumerate(input_data.input_images)
            }

            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result_index, base64_string, file_path, error = future.result()
                except Exception as exc:
                    result_index = index
                    base64_string = None
                    file_path = None
                    error = str(exc)

                image_base64_strings[result_index] = base64_string
                image_file_paths[result_index] = file_path
                if error:
                    self.logger.error(f"Image {result_index} failed: {error}")
                else:
                    self.logger.info(f"Image {result_index} filtered successfully.")

        if len(image_base64_strings) != input_count or len(image_file_paths) != input_count:
            raise RuntimeError(f"Expected {input_count} outputs for each output list.")

        successful_count = sum(
            base64_string is not None or file_path is not None
            for base64_string, file_path in zip(image_base64_strings, image_file_paths)
        )
        failed_count = input_count - successful_count
        self.logger.info(
            f"Completed {input_count} images: {successful_count} succeeded, {failed_count} failed."
        )

        self._set_display_result(image_file_paths)

        return OutputModel(
            image_base64_strings=image_base64_strings,
            image_file_paths=image_file_paths,
            input_count=input_count,
            successful_count=successful_count,
            failed_count=failed_count,
        )

    def _process_image(
        self,
        index: int,
        image_input: Optional[str],
        input_data: InputModel,
    ) -> Tuple[int, Optional[str], Optional[str], Optional[str]]:
        if image_input is None:
            return index, None, None, "Input image is null."

        try:
            image = self._load_image(image_input)
            image = self._apply_filters(image, input_data)
            output_buffer = BytesIO()
            image.save(output_buffer, format="PNG")
            image_bytes = output_buffer.getvalue()
        except Exception as exc:
            return index, None, None, str(exc)

        image_base64_string = None
        image_file_path = None

        if input_data.output_type in (OutputTypeEnum.base64_string, OutputTypeEnum.both):
            image_base64_string = base64.b64encode(image_bytes).decode("utf-8")

        if input_data.output_type in (OutputTypeEnum.file, OutputTypeEnum.both):
            image_file_path = str(Path(self.results_path) / f"filtered_{index}.png")
            with open(image_file_path, "wb") as output_file:
                output_file.write(image_bytes)

        return index, image_base64_string, image_file_path, None

    def _load_image(self, image_input: str) -> Image.Image:
        input_path = Path(image_input)
        if input_path.exists() and input_path.is_file():
            return Image.open(input_path).convert("RGB")

        base64_value = image_input
        if "," in base64_value and base64_value.lower().startswith("data:"):
            base64_value = base64_value.split(",", 1)[1]

        image_bytes = base64.b64decode(base64_value)
        return Image.open(BytesIO(image_bytes)).convert("RGB")

    def _apply_filters(self, image: Image.Image, input_data: InputModel) -> Image.Image:
        if input_data.black_and_white:
            image = ImageOps.grayscale(image).convert("RGB")
        if input_data.sepia:
            image = self._apply_sepia(image)
        if input_data.brightness:
            image = ImageEnhance.Brightness(image).enhance(1.3)
        if input_data.darkness:
            image = ImageEnhance.Brightness(image).enhance(0.7)
        if input_data.contrast:
            image = ImageEnhance.Contrast(image).enhance(1.5)
        if input_data.red:
            image = self._scale_channels(image, red=1.35, green=0.85, blue=0.85)
        if input_data.green:
            image = self._scale_channels(image, red=0.85, green=1.35, blue=0.85)
        if input_data.blue:
            image = self._scale_channels(image, red=0.85, green=0.85, blue=1.35)
        if input_data.cool:
            image = self._scale_channels(image, red=0.85, green=1.0, blue=1.2)
        if input_data.warm:
            image = self._scale_channels(image, red=1.2, green=1.0, blue=0.85)
        return image

    def _apply_sepia(self, image: Image.Image) -> Image.Image:
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                red, green, blue = pixels[x, y]
                tr = int(0.393 * red + 0.769 * green + 0.189 * blue)
                tg = int(0.349 * red + 0.686 * green + 0.168 * blue)
                tb = int(0.272 * red + 0.534 * green + 0.131 * blue)
                pixels[x, y] = (min(255, tr), min(255, tg), min(255, tb))
        return image

    def _scale_channels(
        self,
        image: Image.Image,
        red: float,
        green: float,
        blue: float,
    ) -> Image.Image:
        red_channel, green_channel, blue_channel = image.split()
        red_channel = red_channel.point(lambda value: min(255, int(value * red)))
        green_channel = green_channel.point(lambda value: min(255, int(value * green)))
        blue_channel = blue_channel.point(lambda value: min(255, int(value * blue)))
        return Image.merge("RGB", (red_channel, green_channel, blue_channel))

    def _set_display_result(self, image_file_paths):
        first_file_path = next((path for path in image_file_paths if path is not None), None)
        if first_file_path is None:
            return

        self.display_result = {
            "file_type": "png",
            "file_path": first_file_path,
        }
