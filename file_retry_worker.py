"""Background worker to retry failed cloud uploads and blockchain hash anchoring for files."""

import os
import time

from cloud_storage import upload_bytes
from database import get_all_files, update_file
from algorand import register_file_hash


def _local_payload_for_file(file_record):
    filename = file_record.get('filename')
    if not filename:
        return None

    base_dir = 'uploads/encrypted' if file_record.get('encrypted') else 'uploads/decrypted'
    local_path = os.path.join(base_dir, filename)
    if not os.path.exists(local_path):
        return None

    with open(local_path, 'rb') as f:
        return f.read()


def _needs_cloud_retry(file_record):
    status = str(file_record.get('cloud_status') or '').strip().lower()
    return (not status) or status.startswith('error')


def _needs_chain_retry(file_record):
    status = str(file_record.get('blockchain_status') or '').strip().lower()
    if not file_record.get('file_hash'):
        return False
    return (not status) or status in ('failed',) or status.startswith('error')


def run_once():
    files = get_all_files()
    summary = {
        'scanned': len(files),
        'updated': 0,
        'cloud_retried': 0,
        'chain_retried': 0,
    }
    for record in files:
        file_id = getattr(record, 'doc_id', None)
        if not file_id:
            continue

        updates = {}

        if _needs_cloud_retry(record):
            summary['cloud_retried'] += 1
            payload = _local_payload_for_file(record)
            if payload is not None:
                owner_id = record.get('owner_id')
                owner_role = record.get('owner_role') or 'unknown'
                filename = record.get('filename')
                object_key = f"{owner_role}/{owner_id}/{filename}"
                cloud_result = upload_bytes(object_key, payload)
                updates['cloud_provider'] = cloud_result.get('provider')
                updates['cloud_url'] = cloud_result.get('url')
                updates['cloud_status'] = 'Stored' if cloud_result.get('stored') else f"Error: {cloud_result.get('error')}"
            else:
                updates['cloud_status'] = 'Error: local file missing'

        if _needs_chain_retry(record):
            summary['chain_retried'] += 1
            chain_result = register_file_hash(record.get('file_hash'), reference=record.get('filename') or '')
            updates['blockchain_tx_id'] = chain_result.get('txid')
            updates['blockchain_status'] = chain_result.get('status')
            if not chain_result.get('success') and chain_result.get('status') != 'Skipped':
                updates['blockchain_status'] = f"Error: {chain_result.get('error')}"

        if updates:
            try:
                update_file(file_id, updates)
                summary['updated'] += 1
            except Exception:
                # Keep worker resilient; next loop can retry.
                pass

    return summary


def run_loop(interval_seconds=180):
    while True:
        run_once()
        time.sleep(interval_seconds)


if __name__ == '__main__':
    run_loop()
