from __future__ import annotations

import hashlib
import logging
import re
from functools import lru_cache
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, BotoCoreError

from app.core.config import get_settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

_SHA256_HEX = re.compile(r"^[a-fA-F0-9]{64}$")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def configured() -> bool:
    settings = get_settings()
    return bool(
        settings.b2_key_id
        and settings.b2_application_key
        and settings.b2_bucket
        and settings.b2_s3_endpoint
        and settings.b2_s3_region
    )


def require_storage() -> None:
    if not configured():
        raise AppError(
            "Object storage is not configured. Set B2_KEY_ID, B2_APPLICATION_KEY, "
            "B2_BUCKET, and B2_ENDPOINT_URL (or B2_REGION).",
            status_code=503,
            code="storage_unconfigured",
        )


@lru_cache
def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.b2_s3_endpoint,
        aws_access_key_id=settings.b2_key_id,
        aws_secret_access_key=settings.b2_application_key,
        region_name=settings.b2_s3_region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            # boto3 1.36+ would send x-amz-checksum-* which B2 rejects with 400
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def _error_code(exc: ClientError) -> str:
    return str((exc.response or {}).get("Error", {}).get("Code", "") or "")


def probe_bucket() -> bool:
    """Ensure the private B2 bucket exists, then apply browser CORS."""
    if not configured():
        logger.warning("B2 is not configured; uploads will return 503 until credentials are set")
        return False
    settings = get_settings()
    client = _client()
    try:
        client.head_bucket(Bucket=settings.b2_bucket)
        logger.info("B2 bucket reachable")
    except ClientError as exc:
        code = _error_code(exc)
        if not _create_private_bucket(client, settings.b2_bucket, settings.b2_s3_region):
            logger.warning(
                "B2 bucket %r is missing or inaccessible (%s). Create a private bucket with that "
                "exact name in the B2 dashboard, or use an application key with writeBuckets. "
                "A key alone is not enough — presigned URLs still generate without a bucket, "
                "then the browser PUT fails (often shown as CORS).",
                settings.b2_bucket,
                code or type(exc).__name__,
            )
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("B2 head_bucket failed: %s", type(exc).__name__)
        return False
    apply_browser_cors()
    return True


def _create_private_bucket(client, name: str, region: str) -> bool:
    try:
        params: dict = {"Bucket": name}
        if region:
            params["CreateBucketConfiguration"] = {"LocationConstraint": region}
        try:
            client.create_bucket(**params)
        except ClientError as exc:
            if "LocationConstraint" in str(exc) or _error_code(exc) == "InvalidLocationConstraint":
                client.create_bucket(Bucket=name)
            else:
                raise
        logger.info("Created private B2 bucket %r", name)
        return True
    except ClientError as exc:
        code = _error_code(exc)
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            logger.info("B2 bucket %r already exists", name)
            return True
        logger.warning("B2 create_bucket failed (%s)", code or type(exc).__name__)
        return False
    except Exception:  # noqa: BLE001
        logger.warning("B2 create_bucket failed")
        return False


def ensure_bucket() -> None:
    """Create the private bucket if needed. Raises if the key cannot use/create it."""
    require_storage()
    settings = get_settings()
    client = _client()
    try:
        client.head_bucket(Bucket=settings.b2_bucket)
        return
    except ClientError:
        pass
    if _create_private_bucket(client, settings.b2_bucket, settings.b2_s3_region):
        apply_browser_cors()
        return
    raise AppError(
        f"Backblaze bucket {settings.b2_bucket!r} does not exist and could not be created. "
        "In the B2 dashboard create a private bucket with that exact name. An API key alone is not enough.",
        status_code=503,
        code="storage_bucket_missing",
    )


def put_object_bytes(storage_key: str, data: bytes, mime_type: str) -> None:
    require_storage()
    settings = get_settings()
    try:
        _client().put_object(
            Bucket=settings.b2_bucket,
            Key=storage_key,
            Body=data,
            ContentType=mime_type,
        )
    except ClientError as exc:
        code = _error_code(exc)
        logger.warning("B2 put_object failed: %s", code or type(exc).__name__)
        if code in ("InvalidAccessKeyId", "InvalidSecurity", "SignatureDoesNotMatch"):
            raise AppError(
                "Backblaze rejected the S3 credentials. Create a new Application Key "
                "(not the Master Application Key), allow Read & Write on bucket "
                f"{settings.b2_bucket}, enable Allow List All Bucket Names, then set "
                "B2_KEY_ID and B2_APPLICATION_KEY and restart the API.",
                status_code=503,
                code="storage_bad_credentials",
            ) from exc
        if code in ("404", "NoSuchBucket", "NotFound"):
            raise AppError(
                f"B2 bucket {settings.b2_bucket!r} was not found. Confirm the name and that "
                "B2_REGION / B2_ENDPOINT_URL match the bucket's region shown in the B2 UI.",
                status_code=503,
                code="storage_bucket_missing",
            ) from exc
        raise AppError(
            "Could not store the file in Backblaze B2. Confirm the application key can write to this bucket.",
            status_code=503,
            code="storage_error",
        ) from exc


def apply_browser_cors() -> bool:
    """Allow the frontend origin to PUT/HEAD objects. Does not use AllowedOrigins *."""
    require_storage()
    settings = get_settings()
    origins = [str(o).rstrip("/") for o in settings.cors_origins if o]
    if not origins:
        logger.warning("No CORS_ORIGINS set; browser uploads to B2 will fail")
        return False
    try:
        _client().put_bucket_cors(
            Bucket=settings.b2_bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": origins,
                        "AllowedMethods": ["PUT", "HEAD", "GET"],
                        "AllowedHeaders": ["*"],
                        "ExposeHeaders": ["ETag", "Content-Type", "Content-Length"],
                        "MaxAgeSeconds": 3600,
                    }
                ]
            },
        )
        logger.info("B2 bucket CORS set for %s", ", ".join(origins))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not set B2 CORS (%s). The application key needs writeBucketCors, "
            "or set this on the bucket in B2 (must include s3_put, not only the web UI share toggle): "
            "origins=%s methods=PUT,HEAD",
            type(exc).__name__,
            ", ".join(origins),
        )
        return False


def presigned_put(
    storage_key: str,
    mime_type: str,
    sha256_hex_digest: str,
    *,
    expires: Optional[int] = None,
) -> tuple[str, dict[str, str]]:
    require_storage()
    if not _SHA256_HEX.match(sha256_hex_digest):
        raise AppError("Invalid content hash", status_code=400, code="invalid_hash")
    settings = get_settings()
    ttl = expires if expires is not None else settings.presigned_url_expire_seconds
    # B2 rejects x-amz-checksum-sha256; integrity is enforced on complete() via GET + SHA-256.
    url = _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.b2_bucket,
            "Key": storage_key,
            "ContentType": mime_type,
        },
        ExpiresIn=ttl,
        HttpMethod="PUT",
    )
    return url, {"Content-Type": mime_type}


def head_object(storage_key: str) -> dict:
    require_storage()
    settings = get_settings()
    try:
        resp = _client().head_object(Bucket=settings.b2_bucket, Key=storage_key)
    except ClientError as exc:
        code = (exc.response or {}).get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            raise AppError("Uploaded object not found in storage", status_code=400, code="missing_object") from exc
        raise AppError("Could not inspect uploaded object", status_code=400, code="storage_error") from exc
    except BotoCoreError as exc:
        raise AppError("Could not inspect uploaded object", status_code=400, code="storage_error") from exc
    return {
        "content_length": int(resp.get("ContentLength") or 0),
        "content_type": (resp.get("ContentType") or "").split(";")[0].strip(),
    }


def get_object_bytes(storage_key: str) -> bytes:
    require_storage()
    settings = get_settings()
    try:
        resp = _client().get_object(Bucket=settings.b2_bucket, Key=storage_key)
        return resp["Body"].read()
    except ClientError as exc:
        raise AppError("Could not read uploaded file", status_code=400, code="missing_object") from exc


def delete_object(storage_key: str) -> None:
    if not configured():
        return
    settings = get_settings()
    try:
        _client().delete_object(Bucket=settings.b2_bucket, Key=storage_key)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to delete object key=%s", storage_key[:80])
