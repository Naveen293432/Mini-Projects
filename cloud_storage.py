import os
import importlib
from typing import Dict, List, Optional


def _ensure_local_root(root: str) -> None:
    os.makedirs(root, exist_ok=True)


def list_local_objects(root: Optional[str] = None) -> List[Dict[str, str]]:
    local_root = root or os.environ.get('CLOUD_LOCAL_ROOT', os.path.join('data', 'cloud_storage'))
    if not os.path.isdir(local_root):
        return []

    objects: List[Dict[str, str]] = []
    for dirpath, _, filenames in os.walk(local_root):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            objects.append({
                'key': os.path.relpath(full_path, local_root).replace('\\', '/'),
                'path': os.path.abspath(full_path),
                'size': str(os.path.getsize(full_path)),
                'modified_at': str(int(os.path.getmtime(full_path))),
            })

    objects.sort(key=lambda item: item['key'])
    return objects


def upload_bytes(object_key: str, payload: bytes, content_type: str = 'application/octet-stream') -> Dict[str, Optional[str]]:
    """Upload bytes to configured cloud provider.

    Supported providers:
    - local (default): stores under CLOUD_LOCAL_ROOT
    - s3: uploads to S3-compatible storage when boto3 and credentials are configured
    """
    provider = os.environ.get('CLOUD_PROVIDER', 'local').strip().lower() or 'local'

    if provider == 's3':
        try:
            boto3 = importlib.import_module('boto3')
        except Exception:
            return {
                'stored': False,
                'provider': 's3',
                'key': object_key,
                'url': None,
                'error': 'boto3 not installed',
            }

        bucket = os.environ.get('S3_BUCKET', '').strip()
        region = os.environ.get('S3_REGION', '').strip() or None
        endpoint_url = os.environ.get('S3_ENDPOINT_URL', '').strip() or None
        access_key = os.environ.get('S3_ACCESS_KEY_ID', '').strip() or None
        secret_key = os.environ.get('S3_SECRET_ACCESS_KEY', '').strip() or None

        if not bucket:
            return {
                'stored': False,
                'provider': 's3',
                'key': object_key,
                'url': None,
                'error': 'S3_BUCKET not configured',
            }

        try:
            session = boto3.session.Session()
            client = session.client(
                's3',
                region_name=region,
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            )
            client.put_object(Bucket=bucket, Key=object_key, Body=payload, ContentType=content_type)

            if endpoint_url:
                base = endpoint_url.rstrip('/')
                public_url = f"{base}/{bucket}/{object_key}"
            elif region:
                public_url = f"https://{bucket}.s3.{region}.amazonaws.com/{object_key}"
            else:
                public_url = f"https://{bucket}.s3.amazonaws.com/{object_key}"

            return {
                'stored': True,
                'provider': 's3',
                'key': object_key,
                'url': public_url,
                'error': None,
            }
        except Exception as e:
            return {
                'stored': False,
                'provider': 's3',
                'key': object_key,
                'url': None,
                'error': str(e),
            }

    local_root = os.environ.get('CLOUD_LOCAL_ROOT', os.path.join('data', 'cloud_storage'))
    _ensure_local_root(local_root)
    normalized_key = object_key.replace('\\', '/').lstrip('/')
    local_path = os.path.join(local_root, normalized_key)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    with open(local_path, 'wb') as f:
        f.write(payload)

    return {
        'stored': True,
        'provider': 'local',
        'key': normalized_key,
        'url': os.path.abspath(local_path),
        'error': None,
    }
