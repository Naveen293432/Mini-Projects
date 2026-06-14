import os

try:
    from algosdk.v2client.algod import AlgodClient
except Exception:
    AlgodClient = None

ALGOD_ADDRESS = os.environ.get('ALGOD_ADDRESS', '')
ALGOD_TOKEN = os.environ.get('ALGOD_TOKEN', '')
RECEIVER_ADDRESS = os.environ.get('ALGORAND_RECEIVER_ADDRESS', '')


def get_client():
    """Return an Algod client or raise if not configured."""
    if AlgodClient is None:
        raise RuntimeError('algosdk not installed. Run: pip install py-algorand-sdk')
    if not ALGOD_ADDRESS or not ALGOD_TOKEN:
        raise RuntimeError('ALGOD_ADDRESS or ALGOD_TOKEN not set in environment')
    return AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)


def verify_transaction(txid):
    """Verify a transaction ID on Algorand network.

    Returns a dict with keys:
      - confirmed: bool
      - txinfo: raw transaction info (if available)
      - error: error string (if any)
    """
    if AlgodClient is None:
        return {'confirmed': False, 'error': 'algosdk not installed'}

    try:
        client = get_client()
    except Exception as e:
        return {'confirmed': False, 'error': str(e)}

    try:
        txinfo = client.pending_transaction_info(txid)
        confirmed_round = txinfo.get('confirmed-round', 0)
        confirmed = bool(confirmed_round and confirmed_round > 0)
        return {'confirmed': confirmed, 'txinfo': txinfo}
    except Exception as e:
        return {'confirmed': False, 'error': str(e)}


def register_file_hash(file_hash, reference=''):
    """Anchor a file hash on Algorand using a note transaction.

    Returns:
      - success: bool
      - txid: str | None
      - status: status text
      - error: error text (optional)
    """
    if not file_hash:
        return {'success': False, 'txid': None, 'status': 'Skipped', 'error': 'missing file hash'}

    receiver = os.environ.get('ALGORAND_RECEIVER_ADDRESS', '').strip() or RECEIVER_ADDRESS
    if not receiver:
        return {'success': False, 'txid': None, 'status': 'Skipped', 'error': 'missing ALGORAND_RECEIVER_ADDRESS'}

    # If node config is missing, do not mark as failed; caller can retry later once configured.
    if not (os.environ.get('ALGOD_ADDRESS', '').strip() and os.environ.get('ALGOD_TOKEN', '').strip()):
        return {'success': False, 'txid': None, 'status': 'Skipped', 'error': 'missing ALGOD configuration'}

    note = f'FILE_HASH:{file_hash}'
    if reference:
        note = f'{note}:{reference}'

    try:
        from algorand_server import send_payment
        # Use tiny payment amount by default to maximize network compatibility.
        min_anchor_amount = float(os.environ.get('ALGORAND_FILE_ANCHOR_AMOUNT', '0.001'))
        txid = send_payment(receiver, min_anchor_amount, note=note)
        return {'success': True, 'txid': txid, 'status': 'Submitted'}
    except Exception as e:
        return {'success': False, 'txid': None, 'status': 'Failed', 'error': str(e)}
