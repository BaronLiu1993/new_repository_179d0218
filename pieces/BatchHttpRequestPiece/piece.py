import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple

import requests
from domino.base_piece import BasePiece

from .models import InputModel, OutputModel, RequestConfig


class BatchHttpRequestPiece(BasePiece):

    def piece_function(self, input_data: InputModel):
        if not input_data.requests:
            raise ValueError("At least one request must be provided.")

        request_count = len(input_data.requests)
        max_workers = min(input_data.max_concurrency, request_count)
        self.logger.info(f"Requesting {request_count} URLs with up to {max_workers} concurrent workers.")

        base64_bytes_data_list = [None] * request_count

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(
                    self._fetch_request,
                    index,
                    request_config,
                    input_data.timeout_seconds,
                ): index
                for index, request_config in enumerate(input_data.requests)
            }

            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result_index, encoded_body, status_code, error = future.result()
                except Exception as exc:
                    result_index = index
                    encoded_body = None
                    status_code = None
                    error = str(exc)

                base64_bytes_data_list[result_index] = encoded_body
                if error:
                    self.logger.error(f"Request {result_index} failed: {error}")
                else:
                    self.logger.info(f"Request {result_index} succeeded with status {status_code}.")

        if len(base64_bytes_data_list) != request_count:
            raise RuntimeError(
                f"Expected {request_count} outputs, got {len(base64_bytes_data_list)}."
            )

        successful_count = sum(item is not None for item in base64_bytes_data_list)
        failed_count = request_count - successful_count
        self.logger.info(
            f"Completed {request_count} requests: {successful_count} succeeded, {failed_count} failed."
        )

        return OutputModel(
            base64_bytes_data_list=base64_bytes_data_list,
            requested_count=request_count,
            successful_count=successful_count,
            failed_count=failed_count,
        )

    def _fetch_request(
        self,
        index: int,
        request_config: RequestConfig,
        timeout_seconds: int,
    ) -> Tuple[int, Optional[str], Optional[int], Optional[str]]:
        headers = {}
        if request_config.bearer_token:
            headers["Authorization"] = f"Bearer {request_config.bearer_token}"

        json_body = None
        if request_config.body_json_data:
            try:
                json_body = json.loads(request_config.body_json_data)
            except json.JSONDecodeError as exc:
                return index, None, None, f"Invalid JSON body: {exc}"

        try:
            response = requests.request(
                method=request_config.method.value,
                url=request_config.url,
                headers=headers,
                json=json_body,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            return index, None, status_code, str(exc)

        encoded_body = base64.b64encode(response.content).decode("utf-8")
        return index, encoded_body, response.status_code, None
