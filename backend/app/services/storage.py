import json
import mimetypes
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.client import Config

from app.config import get_settings


class ObjectStorage:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.minio_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint_url,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name=settings.minio_region,
            config=Config(signature_version="s3v4"),
        )

    def ensure_bucket(self) -> None:
        existing = [b["Name"] for b in self.client.list_buckets().get("Buckets", [])]
        if self.bucket not in existing:
            self.client.create_bucket(Bucket=self.bucket)

    def put_json(self, prefix: str, payload: dict) -> str:
        self.ensure_bucket()
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        key = f"{prefix.rstrip('/')}/{ts}.json"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        return f"s3://{self.bucket}/{key}"

    def get_json(self, uri: str) -> dict[str, Any]:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
            raise ValueError("Expected s3://bucket/key URI")
        response = self.client.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
        data = json.loads(response["Body"].read().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Stored artifact must be a JSON object")
        return data

    def put_binary(
        self,
        key: str,
        data: bytes,
        content_type: str | None = None,
    ) -> str:
        self.ensure_bucket()
        if not content_type:
            content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return f"s3://{self.bucket}/{key}"

    def get_binary(self, key: str) -> tuple[bytes, str | None]:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        data = response["Body"].read()
        content_type = response.get("ContentType")
        return data, content_type
