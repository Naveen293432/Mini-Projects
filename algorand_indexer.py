import os

try:
    from algosdk.v2client.indexer import IndexerClient
except Exception:
    IndexerClient = None

INDEXER_ADDRESS = os.environ.get('INDEXER_ADDRESS', '')
INDEXER_TOKEN = os.environ.get('INDEXER_TOKEN', '')


def get_indexer():
    if IndexerClient is None:
        raise RuntimeError('py-algorand-sdk not installed')
    if not INDEXER_ADDRESS:
        raise RuntimeError('INDEXER_ADDRESS not set')
    return IndexerClient(INDEXER_TOKEN, INDEXER_ADDRESS)


def find_transactions_for_address(address, note_prefix=None, min_round=None):
    """Return list of tx dicts involving `address` as receiver or sender.

    Optional `note_prefix` filters by tx note starting bytes (string).
    """
    client = get_indexer()
    # search for transactions where address is receiver
    try:
        q = client.search_transactions(address=address, limit=50)
        txs = q.get('transactions', [])
        if note_prefix:
            filtered = []
            for tx in txs:
                note = tx.get('note')
                if note:
                    try:
                        import base64
                        raw = base64.b64decode(note)
                        if raw.startswith(note_prefix.encode()):
                            filtered.append(tx)
                    except Exception:
                        continue
            return filtered
        return txs
    except Exception as e:
        return []
