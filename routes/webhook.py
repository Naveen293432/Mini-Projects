from flask import Blueprint, request, jsonify, current_app
from database import get_payment_by_invoice, update_payment, get_payment_by_id, get_user_by_id
from utils.emailer import send_email

webhook_bp = Blueprint('webhook', __name__)


@webhook_bp.route('/algorand', methods=['POST'])
def algorand_webhook():
    """Simple webhook endpoint to receive real-time notifications from indexer or 3rd-party.

    Expected JSON:
    {
        "txid": "...",
        "invoice_id": "...",
        "receiver": "...",
        "amount": 123456
    }
    """
    data = request.get_json() or {}
    txid = data.get('txid')
    invoice = data.get('invoice_id')
    if not txid or not invoice:
        return jsonify({'error': 'txid and invoice_id required'}), 400

    payment = get_payment_by_invoice(invoice)
    if not payment:
        return jsonify({'error': 'invoice not found'}), 404

    # mark confirmed
    try:
        update_payment(payment.doc_id, {'algorand_tx_id': txid, 'algorand_status': 'Confirmed'})
        # send email to user if available
        try:
            user = get_user_by_id(payment.get('user_id'))
            if user and getattr(user, 'email', None):
                send_email(user.username, user.email, 'Payment confirmed', f'Your payment {payment.get("fee_name")} was confirmed on-chain. TX: {txid}')
        except Exception:
            pass
        return jsonify({'ok': True})
    except Exception as e:
        current_app.logger.exception('webhook error')
        return jsonify({'error': str(e)}), 500
