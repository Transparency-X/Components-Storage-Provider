# Components-Storage-Provider

Software components meant for reuse across many apps are built around **abstraction, interfaces, and packaging**. For your cloud storage example, the goal is to hide the vendor-specific details behind a single, stable contract so every app talks to "storage" without caring whether it's R2, B2, or S3.

Here is how to design and build it:

## 1. Define the Interface First

Before writing any vendor-specific code, define what operations you need. This becomes your component's public contract.

```python
# storage/interface.py
from abc import ABC, abstractmethod
from typing import BinaryIO, List, Optional
from dataclasses import dataclass

@dataclass
class StoredObject:
    key: str
    size: int
    last_modified: Optional[str] = None
    etag: Optional[str] = None

class StorageProvider(ABC):
    @abstractmethod
    def upload(self, key: str, data: BinaryIO, content_type: str = "application/octet-stream") -> StoredObject:
        """Upload object. Returns metadata."""
        pass

    @abstractmethod
    def download(self, key: str) -> bytes:
        """Download object as bytes."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete object. Returns success."""
        pass

    @abstractmethod
    def list_objects(self, prefix: str = "") -> List[StoredObject]:
        """List objects with optional prefix filter."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        pass
```

Every app uses only `StorageProvider`. The implementation details are hidden.

## 2. Build Vendor Adapters

Implement the interface for each backend. Because R2, B2, and S3 are all S3-compatible, you can reuse most logic, but wrap each with its own credential handling and endpoint configuration.

```python
# storage/adapters.py
import boto3
from botocore.config import Config
from .interface import StorageProvider, StoredObject

class S3CompatibleStorage(StorageProvider):
    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, 
                 bucket: str, region: str = "auto"):
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4")
        )

    def upload(self, key, data, content_type="application/octet-stream"):
        self.client.upload_fileobj(data, self.bucket, key, 
                                   ExtraArgs={"ContentType": content_type})
        return StoredObject(key=key, size=getattr(data, 'seek', lambda: None) or 0)

    def download(self, key):
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)
        return True

    def list_objects(self, prefix=""):
        paginator = self.client.get_paginator("list_objects_v2")
        results = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                results.append(StoredObject(
                    key=obj["Key"],
                    size=obj["Size"],
                    last_modified=str(obj["LastModified"]),
                    etag=obj.get("ETag")
                ))
        return results

    def exists(self, key):
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self.client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise
```

Then create thin factory presets:

```python
# storage/factory.py
from .adapters import S3CompatibleStorage

def cloudflare_r2(account_id: str, access_key: str, secret_key: str, bucket: str):
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    return S3CompatibleStorage(endpoint, access_key, secret_key, bucket)

def backblaze_b2(key_id: str, application_key: str, bucket: str):
    # Backblaze provides S3-compatible endpoints per bucket
    endpoint = f"https://s3.{bucket}.backblazeb2.com"  # or use your specific endpoint
    return S3CompatibleStorage(endpoint, key_id, application_key, bucket)

def aws_s3(access_key: str, secret_key: str, bucket: str, region: str):
    return S3CompatibleStorage(
        endpoint_url=None,  # boto3 uses default AWS endpoints
        access_key=access_key,
        secret_key=secret_key,
        bucket=bucket,
        region=region
    )
```

## 3. Package It for Reuse

To share across "several/many apps," publish it as an internal package. The exact method depends on your stack:

| Stack | Packaging Method | Install Command |
|-------|-----------------|-----------------|
| **Python** | Private GitHub repo + `pip` | `pip install git+https://github.com/yourorg/storage-sdk.git` |
| **Python** | Internal PyPI (Nexus/Artifactory) | `pip install yourorg-storage` |
| **Node.js** | Private npm scope | `npm install @yourorg/storage` |
| **Go** | Go module | `go get github.com/yourorg/storage` |
| **Universal** | Containerized sidecar/gRPC service | HTTP API any app can call |

**Python packaging structure example:**

```
storage-component/
├── storage/
│   ├── __init__.py
│   ├── interface.py
│   ├── adapters.py
│   ├── factory.py
│   └── exceptions.py          # Custom errors (BucketNotFound, AuthError)
├── tests/
├── pyproject.toml
└── README.md
```

`pyproject.toml`:
```toml
[project]
name = "yourorg-storage"
version = "1.0.0"
dependencies = ["boto3>=1.28.0", "botocore"]

[project.optional-dependencies]
dev = ["pytest", "moto"]  # moto for mocking S3 in tests
```

## 4. Configuration-Driven Initialization

Apps should not hardcode vendor choice. Use environment variables or config files:

```python
# In your app
import os
from storage import factory

provider = os.getenv("STORAGE_PROVIDER")  # "r2", "b2", or "s3"

if provider == "r2":
    storage = factory.cloudflare_r2(
        account_id=os.getenv("R2_ACCOUNT_ID"),
        access_key=os.getenv("R2_ACCESS_KEY"),
        secret_key=os.getenv("R2_SECRET_KEY"),
        bucket=os.getenv("R2_BUCKET")
    )
elif provider == "b2":
    storage = factory.backblaze_b2(...)
```

This lets you switch vendors per environment (dev vs prod) without changing app code.

## 5. Add Cross-Cutting Concerns

A reusable component needs more than just upload/download. Add these **inside the component** so every app gets them automatically:

- **Retries & timeouts**: Wrap boto3 calls with `tenacity` or botocore's built-in retries.
- **Logging**: Structured logs for every operation (key, size, duration, status).
- **Metrics**: Emit statsd/Prometheus counters for `storage_upload_total`, `storage_errors_total`.
- **Streaming**: Support streaming uploads/downloads so apps don't load multi-GB files into memory.
- **Presigned URLs**: Generate temporary URLs if apps need to expose direct download links.
- **Checksum validation**: Verify MD5/SHA256 on upload/download.

## 6. Testing Strategy

Because this is shared infrastructure, test it rigorously:

```python
# tests/test_adapters.py
import pytest
from moto import mock_aws
from storage.adapters import S3CompatibleStorage

@mock_aws
def test_upload_and_download():
    client = S3CompatibleStorage(
        endpoint_url=None,  # moto intercepts boto3
        access_key="fake",
        secret_key="fake",
        bucket="test-bucket",
        region="us-east-1"
    )
    # ... test logic
```

Use `moto` to mock S3 for unit tests. For integration tests, run against real dev buckets in each vendor.

## Summary Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   App A     │     │   App B     │     │   App C     │
│  (Python)   │     │  (Node.js)  │     │  (Go/CLI)   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┴───────────────────┘
                           │
              ┌────────────▼────────────┐
              │  Storage Component      │
              │  (Interface + Adapters) │
              │  - upload()             │
              │  - download()           │
              │  - delete()             │
              │  - list()               │
              └────────────┬────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
    ┌─────────┐      ┌─────────┐      ┌─────────┐
    │Cloudflare│      │Backblaze│      │   AWS   │
    │   R2    │      │   B2    │      │   S3    │
    └─────────┘      └─────────┘      └─────────┘
```

**The golden rule:** Apps depend only on the `StorageProvider` interface. They never import `boto3` directly. You can add Wasabi, MinIO, or another S3-compatible vendor later by adding one adapter file—zero changes to existing apps.
