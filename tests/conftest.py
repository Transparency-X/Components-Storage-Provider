"""
Pytest fixtures for storage tests.
"""

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def s3_mock():
    """
    Start moto's S3 mock and create a test bucket.
    """
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-bucket")
        yield client


@pytest.fixture
def storage(s3_mock):
    """
    A BaseS3Storage instance wired to the moto backend.
    """
    from storage._base_s3 import BaseS3Storage

    return BaseS3Storage("test-bucket", s3_mock)
