# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import os
import uuid
from pathlib import Path

# Third party imports
import boto3
from botocore.exceptions import ClientError
from urllib.parse import quote

# Module imports
from plane.utils.exception_logger import log_exception
from storages.backends.s3boto3 import S3Boto3Storage
from django.core.files.storage import FileSystemStorage


class BaseStorageProvider:
    backend = "base"

    def generate_presigned_post(self, object_name, file_type, file_size, expiration=None):
        raise NotImplementedError

    def generate_presigned_url(self, object_name, expiration=None, http_method="GET", disposition="inline", filename=None):
        raise NotImplementedError

    def get_object_metadata(self, object_name):
        raise NotImplementedError

    def copy_object(self, object_name, new_object_name):
        raise NotImplementedError

    def upload_file(self, file_obj, object_name: str, content_type: str = None, extra_args: dict = {}):
        raise NotImplementedError

    def delete_files(self, object_names):
        raise NotImplementedError


class S3Storage(BaseStorageProvider, S3Boto3Storage):
    def url(self, name, parameters=None, expire=None, http_method=None):
        return name

    """S3 storage class to generate presigned URLs for S3 objects"""

    def __init__(self, request=None):
        # Get the AWS credentials and bucket name from the environment
        self.aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
        # Use the AWS_SECRET_ACCESS_KEY environment variable for the secret key
        self.aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        # Use the AWS_S3_BUCKET_NAME environment variable for the bucket name
        self.aws_storage_bucket_name = os.environ.get("AWS_S3_BUCKET_NAME")
        # Use the AWS_REGION environment variable for the region
        self.aws_region = os.environ.get("AWS_REGION")
        # Use the AWS_S3_ENDPOINT_URL environment variable for the endpoint URL
        self.aws_s3_endpoint_url = os.environ.get("AWS_S3_ENDPOINT_URL") or os.environ.get("MINIO_ENDPOINT_URL")
        # Use the SIGNED_URL_EXPIRATION environment variable for the expiration time (default: 3600 seconds)
        self.signed_url_expiration = int(os.environ.get("SIGNED_URL_EXPIRATION", "3600"))

        if os.environ.get("USE_MINIO") == "1":
            # Determine protocol based on environment variable
            if os.environ.get("MINIO_ENDPOINT_SSL") == "1":
                endpoint_protocol = "https"
            else:
                endpoint_protocol = request.scheme if request else "http"
            # Create an S3 client for MinIO
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
                endpoint_url=(f"{endpoint_protocol}://{request.get_host()}" if request else self.aws_s3_endpoint_url),
                config=boto3.session.Config(signature_version="s3v4"),
            )
        else:
            # Create an S3 client
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
                endpoint_url=self.aws_s3_endpoint_url,
                config=boto3.session.Config(signature_version="s3v4"),
            )

    def generate_presigned_post(self, object_name, file_type, file_size, expiration=None):
        """Generate a presigned URL to upload an S3 object"""
        if expiration is None:
            expiration = self.signed_url_expiration
        fields = {"Content-Type": file_type}

        conditions = [
            {"bucket": self.aws_storage_bucket_name},
            ["content-length-range", 1, file_size],
            {"Content-Type": file_type},
        ]

        # Add condition for the object name (key)
        if object_name.startswith("${filename}"):
            conditions.append(["starts-with", "$key", object_name[: -len("${filename}")]])
        else:
            fields["key"] = object_name
            conditions.append({"key": object_name})

        # Generate the presigned POST URL
        try:
            # Generate a presigned URL for the S3 object
            response = self.s3_client.generate_presigned_post(
                Bucket=self.aws_storage_bucket_name,
                Key=object_name,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expiration,
            )
        # Handle errors
        except ClientError as e:
            print(f"Error generating presigned POST URL: {e}")
            return None

        return response

    def _get_content_disposition(self, disposition, filename=None):
        """Helper method to generate Content-Disposition header value"""
        if filename is None:
            filename = uuid.uuid4().hex

        if filename:
            # Encode the filename to handle special characters
            encoded_filename = quote(filename)
            return f"{disposition}; filename*=UTF-8''{encoded_filename}"
        return disposition

    def generate_presigned_url(
        self,
        object_name,
        expiration=None,
        http_method="GET",
        disposition="inline",
        filename=None,
    ):
        """Generate a presigned URL to share an S3 object"""
        if expiration is None:
            expiration = self.signed_url_expiration
        content_disposition = self._get_content_disposition(disposition, filename)
        try:
            response = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.aws_storage_bucket_name,
                    "Key": str(object_name),
                    "ResponseContentDisposition": content_disposition,
                },
                ExpiresIn=expiration,
                HttpMethod=http_method,
            )
        except ClientError as e:
            log_exception(e)
            return None

        # The response contains the presigned URL
        return response

    def get_object_metadata(self, object_name):
        """Get the metadata for an S3 object"""
        try:
            response = self.s3_client.head_object(Bucket=self.aws_storage_bucket_name, Key=object_name)
        except ClientError as e:
            log_exception(e)
            return None

        return {
            "ContentType": response.get("ContentType"),
            "ContentLength": response.get("ContentLength"),
            "LastModified": (response.get("LastModified").isoformat() if response.get("LastModified") else None),
            "ETag": response.get("ETag"),
            "Metadata": response.get("Metadata", {}),
        }

    def copy_object(self, object_name, new_object_name):
        """Copy an S3 object to a new location"""
        try:
            response = self.s3_client.copy_object(
                Bucket=self.aws_storage_bucket_name,
                CopySource={"Bucket": self.aws_storage_bucket_name, "Key": object_name},
                Key=new_object_name,
            )
        except ClientError as e:
            log_exception(e)
            return None

        return response

    def upload_file(
        self,
        file_obj,
        object_name: str,
        content_type: str = None,
        extra_args: dict = {},
    ) -> bool:
        """Upload a file directly to S3"""
        try:
            if content_type:
                extra_args["ContentType"] = content_type

            self.s3_client.upload_fileobj(
                file_obj,
                self.aws_storage_bucket_name,
                object_name,
                ExtraArgs=extra_args,
            )
            return True
        except ClientError as e:
            log_exception(e)
            return False

    def delete_files(self, object_names):
        """Delete an S3 object"""
        try:
            self.s3_client.delete_objects(
                Bucket=self.aws_storage_bucket_name,
                Delete={"Objects": [{"Key": object_name} for object_name in object_names]},
            )
            return True
        except ClientError as e:
            log_exception(e)
            return False


class LocalFileStorage(BaseStorageProvider):
    backend = "local"

    def __init__(self, request=None):
        self.request = request
        self.base_dir = Path(os.environ.get("LOCAL_FILE_STORAGE_ROOT", "/tmp/plane-cde-storage")).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.fs = FileSystemStorage(location=str(self.base_dir), base_url="/local-file-storage/")

    def _full_path(self, object_name):
        return self.base_dir / str(object_name)

    def generate_presigned_post(self, object_name, file_type, file_size, expiration=None):
        return {
            "backend": self.backend,
            "method": "server-upload",
            "url": None,
            "fields": {
                "key": object_name,
                "Content-Type": file_type,
                "Content-Length": file_size,
            },
        }

    def generate_presigned_url(self, object_name, expiration=None, http_method="GET", disposition="inline", filename=None):
        return str(object_name)

    def get_object_metadata(self, object_name):
        path = self._full_path(object_name)
        if not path.exists():
            return None
        stat = path.stat()
        return {
            "ContentType": None,
            "ContentLength": stat.st_size,
            "LastModified": None,
            "ETag": None,
            "Metadata": {"backend": self.backend},
        }

    def copy_object(self, object_name, new_object_name):
        src = self._full_path(object_name)
        dst = self._full_path(new_object_name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        return True

    def upload_file(self, file_obj, object_name: str, content_type: str = None, extra_args: dict = {}):
        dst = self._full_path(object_name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("wb") as f:
            while True:
                chunk = file_obj.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        return True

    def delete_files(self, object_names):
        for object_name in object_names:
            path = self._full_path(object_name)
            if path.exists():
                path.unlink()
        return True


def storage_backend_name():
    explicit = os.environ.get("FILE_STORAGE_PROVIDER", "").strip().lower()
    if explicit in {"local", "filesystem", "file"}:
        return "local"
    if explicit in {"s3", "minio"}:
        return "s3"

    use_minio = os.environ.get("USE_MINIO") == "1"
    has_s3 = bool(os.environ.get("AWS_S3_BUCKET_NAME") and (os.environ.get("AWS_S3_ENDPOINT_URL") or os.environ.get("AWS_REGION")))
    return "s3" if (use_minio or has_s3) else "local"


def get_storage(request=None, is_server=False):
    backend = storage_backend_name()
    if backend == "local":
        return LocalFileStorage(request=request)
    return S3Storage(request=request)
