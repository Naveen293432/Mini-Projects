import os
from base64 import b64encode

try:
    from algosdk import account, mnemonic
    from algosdk.v2client.algod import AlgodClient
    from algosdk.transaction import PaymentTxn
    from algosdk import transaction
except Exception:
    # modules may not be installed in environment; functions will raise at runtime
    account = None
    mnemonic = None
    AlgodClient = None
    PaymentTxn = None

ALGOD_ADDRESS = os.environ.get('ALGOD_ADDRESS', '')
ALGOD_TOKEN = os.environ.get('ALGOD_TOKEN', '')
SERVER_MNEMONIC = os.environ.get('ALGORAND_SERVER_MNEMONIC', '')


def get_server_account():
    if not SERVER_MNEMONIC:
        raise RuntimeError('ALGORAND_SERVER_MNEMONIC not set')
    if mnemonic is None:
        raise RuntimeError('py-algorand-sdk not installed')
    pk = mnemonic.to_public_key(SERVER_MNEMONIC)
    sk = mnemonic.to_private_key(SERVER_MNEMONIC)
    return pk, sk


def get_client():
    if AlgodClient is None:
        raise RuntimeError('py-algorand-sdk not installed')
    if not ALGOD_ADDRESS or not ALGOD_TOKEN:
        raise RuntimeError('ALGOD_ADDRESS or ALGOD_TOKEN not configured')
    return AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)


def send_payment(to_address, amount_algo, note=None):
    """Send ALGO from server account to `to_address`.

    amount_algo: float ALGO amount (converted to microAlgos)
    Returns txid on success.
    """
    pk, sk = get_server_account()
    client = get_client()
    params = client.suggested_params()
    micro = int(amount_algo * 1_000_000)
    txn = PaymentTxn(pk, params, to_address, micro)
    if note:
        txn.note = note.encode() if isinstance(note, str) else note
    signed = txn.sign(sk)
    txid = client.send_transaction(signed)
    return txid
