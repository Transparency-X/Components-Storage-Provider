"""
Tests for the BaseS3Storage adapter using moto.
"""

import io

import pytest

from storage.interface import ObjectNotFoundError, StoredObject


def test_upload_and_download(storage):
    key = "folder/hello.txt"
    content = b"Hello, world!"

    # Upload
    data = io.BytesIO(content)
    obj = storage.upload_fileobj(key, data, content_type="text/plain")
    assert obj.key == key
    assert obj.size == len(content)

    # Exists
    assert storage.exists(key) is True

    # Head
    meta = storage.head(key)
    assert meta.size == len(content)

    # Download bytes
    result = storage.download_bytes(key)
    assert result == content

    # Download fileobj
    buf = io.BytesIO()
    storage.download_fileobj(key, buf)
    buf.seek(0)
    assert buf.read() == content


def test_delete(storage):
    key = "temp.txt"
    storage.upload_fileobj(key, io.BytesIO(b"temp"))
    storage.delete(key)
    assert not storage.exists(key)

    with pytest.raises(ObjectNotFoundError):
        storage.delete(key)


def test_list_objects(storage):
    for i in range(5):
        storage.upload_fileobj(f"test/{i}.txt", io.BytesIO(b"data"))

    # Unfiltered
    objects = list(storage.list_objects())
    assert len(objects) == 5

    # Filtered by prefix
    objects = list(storage.list_objects(prefix="test/"))
    assert len(objects) == 5

    objects = list(storage.list_objects(prefix="other/"))
    assert len(objects) == 0

    # max_keys
    objects = list(storage.list_objects(max_keys=2))
    assert len(objects) <= 2  # max_keys is an upper limit


def test_presigned_url(storage):
    key = "shared.txt"
    storage.upload_fileobj(key, io.BytesIO(b"shared"))
    url = storage.presigned_url(key, expiration=60)
    assert "test-bucket" in url
    assert "X-Amz-Expires=60" in url


def test_object_not_found(storage):
    with pytest.raises(ObjectNotFoundError):
        storage.download_bytes("nonexistent")

    with pytest.raises(ObjectNotFoundError):
        storage.head("nonexistent")
