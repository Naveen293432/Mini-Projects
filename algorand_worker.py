"""Background worker to verify pending Algorand payments.

Run this periodically (cron, supervisor) or trigger from admin UI.
"""
import time
from algorand import verify_transaction
from database import get_all_payments, update_payment
import os

# Optional use of Indexer to detect incoming payments to configured receiver
USE_INDEXER = bool(os.environ.get('USE_ALGORAND_INDEXER', '').lower() in ('1', 'true', 'yes'))
INDEXER_ADDRESS = os.environ.get('INDEXER_ADDRESS', '')
from algorand_indexer import find_transactions_for_address


RECEIVER_ADDRESS = os.environ.get('ALGORAND_RECEIVER_ADDRESS', '')
from utils.emailer import send_email
from database import get_user_by_id


def run_once():
    payments = get_all_payments()
    for p in payments:
        # If a tx id is provided, verify it as before
        if p.get('algorand_status') == 'Pending' and p.get('algorand_tx_id'):
            txid = p.get('algorand_tx_id')
            res = verify_transaction(txid)
            status = 'Pending'
            if res.get('confirmed'):
                status = 'Confirmed'
            elif res.get('error'):
                status = 'Error: ' + str(res.get('error'))
            try:
                update_payment(p.doc_id, {'algorand_status': status})
            except Exception:
                pass

    # If indexer is enabled, scan receiver address for incoming txs and match to unpaid payments
    if USE_INDEXER and RECEIVER_ADDRESS:
        try:
            txs = find_transactions_for_address(RECEIVER_ADDRESS)
            # For each tx, if note or other metadata links to a payment, mark it confirmed
            for tx in txs:
                # attempt to extract note or sender and amount
                note = tx.get('note')
                txid = tx.get('id')
                sender = tx.get('sender')
                payment_found = None
                # Attempt to decode note (base64) and match invoice id
                decoded_note = None
                if note:
                    try:
                        import base64
                        decoded_note = base64.b64decode(note).decode(errors='ignore')
                    except Exception:
                        decoded_note = None
                # First try to match invoice id from note
                if decoded_note:
                    for p in payments:
                        if p.get('invoice_id') and p.get('invoice_id') == decoded_note:
                            payment_found = p
                            break
                # Try to match by tx id
                for p in payments:
                    if p.get('algorand_tx_id') == txid:
                        payment_found = p
                        break
                # If not matched, try to match by amount and sender and pending status
                if not payment_found:
                    amt = None
                    payment_amount = None
                    try:
                        amt = tx.get('payment-transaction', {}).get('amount')
                    except Exception:
                        amt = None
                    for p in payments:
                        if p.get('algorand_status') in (None, 'Not Applicable'):
                            continue
                        # skip already confirmed
                        if p.get('algorand_status') == 'Confirmed':
                            continue
                        # compare microAlgos: payment.amount is assumed in ALGO; convert
                        try:
                            payment_amount = int(float(p.get('amount', 0)) * 1_000_000)
                        except Exception:
                            payment_amount = None
                        if amt is not None and payment_amount is not None and amt == payment_amount:
                            # match by amount and (optionally) sender
                            payment_found = p
                            break
                if payment_found:
                    try:
                        update_payment(payment_found.doc_id, {'algorand_tx_id': txid, 'algorand_status': 'Confirmed'})
                        # send receipt email if possible
                        try:
                            user = get_user_by_id(payment_found.get('user_id'))
                            if user and getattr(user, 'email', None):
                                send_email(user.username, user.email, 'Payment confirmed', f'Your payment {payment_found.get("fee_name")} was confirmed on-chain. TX: {txid}')
                        except Exception:
                            pass
                    except Exception:
                        pass
        except Exception:
            # ignore indexer errors
            pass


def run_loop(interval_seconds=60):
    while True:
        run_once()
        time.sleep(interval_seconds)


if __name__ == '__main__':
    run_loop()
