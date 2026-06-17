import os
import hashlib
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from functools import wraps
from werkzeug.utils import secure_filename
from database import (
    get_all_fees, get_fee_by_id, create_payment, get_payments_by_user,
    create_complaint, get_complaints_by_user,
    get_files_by_owner, create_file_record, get_file_by_id, get_all_files,
    create_secret, get_secrets_for_role, get_all_secrets,
    create_audit_log, get_user_keys, store_user_keys, get_payment_by_id, update_payment
)
from database import set_user_currency, get_user_currency, get_user_by_id, set_user_bank_details, get_user_bank_details
from flask import make_response
import algorand
from utils.emailer import send_email
from utils.currency import usd_to_algo, algo_to_microalgo, format_currency, usd_to_inr
import qrcode
import io
import base64
import logging
from urllib.parse import urlencode
from urllib.parse import urlparse
from encryption import encrypt_file_hybrid, decrypt_file_hybrid, generate_rsa_keypair
from cloud_storage import upload_bytes
from cloud_storage import list_local_objects

user_bp = Blueprint('user', __name__)


def _build_invoice_uri(receiver, micro_algo_amount, invoice_id):
    normalized_receiver = _normalize_algorand_address(receiver)
    if not normalized_receiver:
        return None

    # Use an amount-only URI for maximum wallet compatibility when scanning QR.
    # Some wallets throw generic scan errors when note/xnote params are present.
    params = {
        'amount': str(int(micro_algo_amount)),
    }

    return f"algorand://{normalized_receiver}?{urlencode(params)}"


def _normalize_algorand_address(receiver):
    raw = (receiver or '').strip()
    if not raw:
        return ''

    # Accept either plain addresses or accidental URI values in env config.
    candidate = raw
    if '://' in raw:
        parsed = urlparse(raw)
        candidate = (parsed.path or '').lstrip('/') or (parsed.netloc or '')

    candidate = (candidate or '').split('?', 1)[0].split('#', 1)[0].strip().upper()
    if not candidate:
        return ''

    try:
        from algosdk import encoding as algo_encoding
        if not algo_encoding.is_valid_address(candidate):
            logging.warning('Invalid ALGORAND_RECEIVER_ADDRESS value: %s', raw)
            return ''
    except Exception:
        # If SDK is unavailable, still return sanitized value.
        pass

    return candidate


def _build_upi_uri(upi_id, payee_name, amount_inr, transaction_note=''):
    """Build a UPI payment URI for QR code generation.
    
    Args:
        upi_id: User's UPI ID (e.g., user@bank)
        payee_name: Name to show for payment (max 60 chars, only alphanumeric, space, hyphen, dot)
        amount_inr: Amount in Indian Rupees
        transaction_note: Transaction reference (max 80 chars)
    """
    if not upi_id or not upi_id.strip():
        return None
    
    upi_id = upi_id.strip()
    payee_name = (payee_name or '').strip()
    
    # Sanitize payee name: only alphanumeric, spaces, hyphens, dots
    if payee_name:
        payee_name = ''.join(c for c in payee_name if c.isalnum() or c in (' ', '-', '.'))[:60]
    
    # Sanitize note: remove special chars that might break URI
    if transaction_note:
        transaction_note = ''.join(c for c in transaction_note if c.isalnum() or c in (' ', '-', '_', '.'))[:80]
    
    # Build UPI string carefully: upi://pay?pa=UPI_ID&pn=NAME&am=AMOUNT&tn=NOTE
    # Note: Don't use urlencode as it may cause issues with UPI parsing
    uri_parts = []
    uri_parts.append(f"pa={upi_id}")
    
    if payee_name:
        uri_parts.append(f"pn={payee_name}")
    
    if amount_inr and amount_inr > 0:
        # Format amount without currency symbol, just the number
        uri_parts.append(f"am={float(amount_inr):.2f}")
    
    if transaction_note:
        uri_parts.append(f"tn={transaction_note}")
    
    return f"upi://pay?{'&'.join(uri_parts)}"


def user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'user':
            flash('Access denied. User privileges required.', 'error')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


@user_bp.route('/dashboard')
@login_required
@user_required
def dashboard():
    payments = get_payments_by_user(current_user.id)
    complaints = get_complaints_by_user(current_user.id)
    files = get_files_by_owner(current_user.id)
    
    stats = {
        'total_payments': len(payments),
        'total_spent': sum(p.get('amount', 0) for p in payments),
        'active_complaints': len([c for c in complaints if c.get('status') != 'Resolved']),
        'total_files': len(files)
    }
    return render_template(
        'user/dashboard.html',
        stats=stats,
        db_path=os.path.abspath(os.path.join('data', 'database.json')),
        cloud_root=os.path.abspath(os.environ.get('CLOUD_LOCAL_ROOT', os.path.join('data', 'cloud_storage'))),
        file_records=files,
        cloud_objects=list_local_objects(os.path.abspath(os.environ.get('CLOUD_LOCAL_ROOT', os.path.join('data', 'cloud_storage')))),
    )


@user_bp.route('/fees')
@login_required
@user_required
def fee_payment():
    fees = get_all_fees()
    payments = get_payments_by_user(current_user.id)
    return render_template('user/fees.html', fees=fees, payments=payments)


@user_bp.route('/fees/<fee_id>/pay', methods=['POST'])
@login_required
@user_required
def pay_fee(fee_id):
    fee = get_fee_by_id(fee_id)
    if fee:
        # Support optional Algorand tx id supplied by user (user may pay from external wallet)
        alg_txid = request.form.get('algorand_txid') if request.form else None

        # payment currency selection
        pay_currency = request.form.get('pay_currency', 'usd')

        # create payment record (includes generated invoice_id)
        payment_id = create_payment(
            current_user.id,
            current_user.username,
            fee_id,
            fee.get('name'),
            fee.get('amount'),
            algorand_tx_id=alg_txid,
            paid_currency=pay_currency
        )

        # If an algorand txid was provided, verify it and update the payment status
        if alg_txid:
            verify = algorand.verify_transaction(alg_txid)
            status = 'Pending'
            if verify.get('confirmed'):
                status = 'Confirmed'
            elif verify.get('error'):
                status = 'Error: ' + str(verify.get('error'))
            try:
                update_payment(payment_id, {'algorand_status': status})
            except Exception:
                pass

        # Retrieve payment to get invoice id for user guidance
        payment = get_payment_by_id(payment_id)
        invoice = payment.get('invoice_id') if payment else None

        create_audit_log(current_user.id, current_user.username, 'Payment Made', f'Paid fee: {fee.get("name")}' + (f' (alg_tx: {alg_txid})' if alg_txid else ''))
        if alg_txid and payment and payment.get('algorand_status') == 'Confirmed':
            # send receipt email
            try:
                send_email(payment.get('user_name'), get_user_by_id(current_user.id).email, f'Payment confirmed: {payment.get("fee_name")}', f'Your payment was confirmed on-chain. TX: {alg_txid}')
            except Exception:
                pass
            flash('Payment recorded and transaction confirmed on-chain.', 'success')
        else:
            # Redirect user to invoice page where QR and invoice are shown
            if invoice:
                return redirect(url_for('user.show_invoice', payment_id=payment_id))
            flash('Payment recorded. If you supplied an Algorand tx id it will be verified shortly.', 'success')
    else:
        flash('Fee not found.', 'error')
    return redirect(url_for('user.fee_payment'))



@user_bp.route('/fees/invoice/<payment_id>')
@login_required
@user_required
def show_invoice(payment_id):
    payment = get_payment_by_id(payment_id)
    if not payment:
        flash('Invoice not found.', 'error')
        return redirect(url_for('user.fee_payment'))

    # Build Algorand payment URI with real amount in microALGO
    receiver = os.environ.get('ALGORAND_RECEIVER_ADDRESS', '')
    amount_usd = payment.get('amount', 0)
    invoice = payment.get('invoice_id')
    
    # Convert USD to ALGO amount
    algo_amount = usd_to_algo(amount_usd)
    micro_algo_amount = algo_to_microalgo(algo_amount)
    
    # Build URI with amount and note
    uri = _build_invoice_uri(receiver, micro_algo_amount, invoice)
    if not uri:
        logging.warning('Unable to build invoice URI for payment %s due to missing/invalid receiver address', payment_id)
    
    # Provide a URL for the QR image (served by a separate route)
    qr_url = url_for('user.invoice_qr', payment_id=payment_id) if uri else None
    
    # Add formatted amounts to payment dict for display
    payment['algo_amount'] = algo_amount
    payment['formatted_usd'] = format_currency(amount_usd, 'usd')
    
    return render_template('user/invoice.html', payment=payment, qr_url=qr_url, uri=uri)



@user_bp.route('/fees/invoice/<payment_id>/qr.png')
@login_required
@user_required
def invoice_qr(payment_id):
    payment = get_payment_by_id(payment_id)
    if not payment:
        flash('Invoice not found.', 'error')
        return ('', 404)

    # Only owner can fetch their invoice QR
    if str(payment.get('user_id')) != str(current_user.id):
        flash('Access denied.', 'error')
        return ('', 403)

    receiver = os.environ.get('ALGORAND_RECEIVER_ADDRESS', '')
    invoice = payment.get('invoice_id')
    amount_usd = payment.get('amount', 0)
    
    # Convert USD to ALGO and then to microALGO
    algo_amount = usd_to_algo(amount_usd)
    micro_algo_amount = algo_to_microalgo(algo_amount)
    
    # Build URI with real amount
    uri = _build_invoice_uri(receiver, micro_algo_amount, invoice)
    if not uri:
        logging.warning('Missing or invalid ALGORAND_RECEIVER_ADDRESS; cannot render QR for invoice %s', invoice)
        return ('', 400)

    try:
        try:
            qr_img = qrcode.make(uri)
        except Exception:
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(uri)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        buf.seek(0)
        return send_file(buf, mimetype='image/png')
    except Exception:
        logging.exception('Failed to render QR PNG for invoice %s', invoice)
        return ('', 500)


@user_bp.route('/fees/bank-transfer/<payment_id>')
@login_required
@user_required
def show_bank_payment(payment_id):
    """Display bank transfer details for a payment."""
    payment = get_payment_by_id(payment_id)
    if not payment:
        flash('Payment not found.', 'error')
        return redirect(url_for('user.fee_payment'))

    # Only owner can view their payment
    if str(payment.get('user_id')) != str(current_user.id):
        flash('Access denied.', 'error')
        return redirect(url_for('user.fee_payment'))

    # Get admin's bank details to display for receiving payment
    user_doc = get_user_by_id(current_user.id)
    bank_details = get_user_bank_details(current_user.id)
    
    # Add formatted amounts to payment dict for display
    amount_usd = payment.get('amount', 0)
    payment['formatted_usd'] = format_currency(amount_usd, 'usd')
    
    # Check if admin has bank details set up
    has_bank_details = bool(bank_details.get('upi_id') or bank_details.get('bank_account_number'))
    
    qr_url = None
    if bank_details.get('upi_id'):
        qr_url = url_for('user.bank_payment_qr', payment_id=payment_id)
    
    return render_template('user/bank_payment.html', 
                         payment=payment, 
                         bank_details=bank_details,
                         has_bank_details=has_bank_details,
                         qr_url=qr_url)


@user_bp.route('/fees/bank-transfer/<payment_id>/qr.png')
@login_required
@user_required
def bank_payment_qr(payment_id):
    """Generate UPI QR code for bank transfer payment."""
    payment = get_payment_by_id(payment_id)
    if not payment:
        return ('', 404)

    # Only owner can fetch their payment QR
    if str(payment.get('user_id')) != str(current_user.id):
        return ('', 403)

    bank_details = get_user_bank_details(current_user.id)
    upi_id = bank_details.get('upi_id', '')
    
    if not upi_id:
        logging.warning('User %s has no UPI ID set; cannot generate QR', current_user.id)
        return ('', 400)

    amount_usd = payment.get('amount', 0)
    # Convert USD to INR for UPI QR code
    amount_inr = usd_to_inr(amount_usd)
    
    payee_name = bank_details.get('bank_account_name', '')
    invoice_id = payment.get('invoice_id', '')
    
    # Build UPI URI with INR amount
    uri = _build_upi_uri(upi_id, payee_name, amount_inr, f'Inv-{invoice_id}')
    if not uri:
        logging.warning('Failed to build UPI URI for payment %s', payment_id)
        return ('', 400)

    try:
        try:
            qr_img = qrcode.make(uri)
        except Exception:
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(uri)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        buf.seek(0)
        return send_file(buf, mimetype='image/png')
    except Exception:
        logging.exception('Failed to render UPI QR PNG for payment %s', payment_id)
        return ('', 500)


@user_bp.route('/complaints')
@login_required
@user_required
def complaints():
    complaints = get_complaints_by_user(current_user.id)
    return render_template('user/complaints.html', complaints=complaints)


@user_bp.route('/complaints/submit', methods=['POST'])
@login_required
@user_required
def submit_complaint():
    category = request.form.get('category', '').strip()
    priority = request.form.get('priority', 'Medium')
    subject = request.form.get('subject', '').strip()
    description = request.form.get('description', '').strip()
    
    if category and subject and description:
        create_complaint(
            current_user.id,
            current_user.username,
            category,
            priority,
            subject,
            description
        )
        create_audit_log(current_user.id, current_user.username, 'Complaint Submitted', f'Submitted complaint: {subject}')
        flash('Complaint submitted successfully.', 'success')
    else:
        flash('Please fill in all required fields.', 'error')
    
    return redirect(url_for('user.complaints'))


@user_bp.route('/upload')
@login_required
@user_required
def file_upload():
    files = get_files_by_owner(current_user.id)
    return render_template('user/upload.html', files=files)


@user_bp.route('/upload/file', methods=['POST'])
@login_required
@user_required
def upload_file():
    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('user.file_upload'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('user.file_upload'))
    
    if file:
        try:
            original_filename = secure_filename(file.filename)
            file_data = file.read()
            file_size = len(file_data)

            keys = get_user_keys(current_user.id)
            if not keys:
                public_key, private_key = generate_rsa_keypair()
                store_user_keys(current_user.id, public_key, private_key)
                keys = {'public_key': public_key, 'private_key': private_key}

            encrypted_data = encrypt_file_hybrid(file_data, keys['public_key'])
            filename = f"user_{current_user.id}_{original_filename}"
            filepath = os.path.join('uploads/encrypted', filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            with open(filepath, 'wb') as f:
                f.write(encrypted_data)

            file_hash = hashlib.sha256(encrypted_data).hexdigest()
            cloud_key = f"users/{current_user.id}/{filename}"
            cloud_result = upload_bytes(cloud_key, encrypted_data)
            chain_result = algorand.register_file_hash(file_hash, reference=filename)

            create_file_record(
                filename,
                original_filename,
                current_user.id,
                'user',
                True,
                file_size,
                file_hash=file_hash,
                cloud_provider=cloud_result.get('provider'),
                cloud_url=cloud_result.get('url'),
                cloud_status='Stored' if cloud_result.get('stored') else f"Error: {cloud_result.get('error')}",
                blockchain_tx_id=chain_result.get('txid'),
                blockchain_status=chain_result.get('status'),
            )
            create_audit_log(current_user.id, current_user.username, 'File Encrypted', f'Encrypted and uploaded: {original_filename}')

            if cloud_result.get('stored'):
                flash('File encrypted, uploaded, and cloud backup stored.', 'success')
            else:
                flash(f"File encrypted locally. Cloud backup failed: {cloud_result.get('error')}", 'warning')

            if chain_result.get('success'):
                flash(f"Blockchain anchor submitted. TxID: {chain_result.get('txid')}", 'success')
            elif chain_result.get('status') == 'Skipped':
                flash(f"Blockchain anchor skipped: {chain_result.get('error')}", 'warning')
            else:
                flash(f"Blockchain anchor failed: {chain_result.get('error')}", 'warning')
        except Exception as e:
            flash(f'Upload failed: {str(e)}', 'error')
    
    return redirect(url_for('user.file_upload'))


@user_bp.route('/download')
@login_required
@user_required
def file_download():
    my_files = get_files_by_owner(current_user.id)
    all_files = get_all_files()
    shared_files = [f for f in all_files if f.get('owner_role') == 'dbmanager']
    return render_template('user/download.html', my_files=my_files, shared_files=shared_files)


@user_bp.route('/download/<file_id>/encrypted')
@login_required
@user_required
def download_encrypted(file_id):
    file_record = get_file_by_id(file_id)
    if not file_record:
        flash('File not found.', 'error')
        return redirect(url_for('user.file_download'))
    
    filename = file_record.get('filename')
    if file_record.get('encrypted'):
        filepath = os.path.join('uploads/encrypted', filename)
    else:
        filepath = os.path.join('uploads/decrypted', filename)
    
    if os.path.exists(filepath):
        create_audit_log(current_user.id, current_user.username, 'File Downloaded', f'Downloaded encrypted: {filename}')
        return send_file(filepath, as_attachment=True, download_name=f"encrypted_{file_record.get('original_filename')}")
    
    flash('File not found on server.', 'error')
    return redirect(url_for('user.file_download'))


@user_bp.route('/download/<file_id>/decrypted')
@login_required
@user_required
def download_decrypted(file_id):
    file_record = get_file_by_id(file_id)
    if not file_record:
        flash('File not found.', 'error')
        return redirect(url_for('user.file_download'))
    
    filename = file_record.get('filename')
    
    if file_record.get('encrypted'):
        filepath = os.path.join('uploads/encrypted', filename)
        
        if not os.path.exists(filepath):
            flash('File not found on server.', 'error')
            return redirect(url_for('user.file_download'))
        
        owner_id = file_record.get('owner_id')
        keys = get_user_keys(str(owner_id))
        
        if not keys:
            flash('Encryption keys not found. You may not have permission to decrypt this file.', 'error')
            return redirect(url_for('user.file_download'))
        
        with open(filepath, 'rb') as f:
            encrypted_data = f.read()
        
        try:
            decrypted_data = decrypt_file_hybrid(encrypted_data, keys['private_key'])
            
            temp_filepath = os.path.join('uploads/decrypted', f"temp_user_{file_record.get('original_filename')}")
            with open(temp_filepath, 'wb') as f:
                f.write(decrypted_data)
            
            create_audit_log(current_user.id, current_user.username, 'File Decrypted', f'Downloaded decrypted: {filename}')
            
            return send_file(temp_filepath, as_attachment=True, download_name=file_record.get('original_filename'))
        except Exception as e:
            flash(f'Decryption failed: {str(e)}', 'error')
            return redirect(url_for('user.file_download'))
    else:
        filepath = os.path.join('uploads/decrypted', filename)
        if os.path.exists(filepath):
            create_audit_log(current_user.id, current_user.username, 'File Downloaded', f'Downloaded: {filename}')
            return send_file(filepath, as_attachment=True, download_name=file_record.get('original_filename'))
    
    flash('File not found on server.', 'error')
    return redirect(url_for('user.file_download'))


@user_bp.route('/history')
@login_required
@user_required
def service_history():
    payments = get_payments_by_user(current_user.id)
    complaints = get_complaints_by_user(current_user.id)
    files = get_files_by_owner(current_user.id)
    
    history = []
    
    for p in payments:
        history.append({
            'type': 'Payment',
            'description': f"Paid {p.get('fee_name')}: ${p.get('amount')}",
            'date': p.get('created_at', ''),
            'status': p.get('status', 'Completed')
        })
    
    for c in complaints:
        history.append({
            'type': 'Complaint',
            'description': f"{c.get('subject')}",
            'date': c.get('created_at', ''),
            'status': c.get('status', 'Pending')
        })
    
    for f in files:
        history.append({
            'type': 'File',
            'description': f"Uploaded: {f.get('original_filename')}",
            'date': f.get('created_at', ''),
            'status': 'Encrypted' if f.get('encrypted') else 'Plain'
        })
    
    history = sorted(history, key=lambda x: x.get('date', ''), reverse=True)
    
    return render_template('user/history.html', history=history)


@user_bp.route('/secrets')
@login_required
@user_required
def secrets():
    my_secrets = get_secrets_for_role('user')
    all_secrets = get_all_secrets()
    return render_template('user/secrets.html', my_secrets=my_secrets, all_secrets=all_secrets)


@user_bp.route('/secrets/share', methods=['POST'])
@login_required
@user_required
def share_secret():
    recipient_role = request.form.get('recipient_role')
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    
    if recipient_role and title and content:
        create_secret(
            current_user.id,
            current_user.username,
            current_user.role,
            recipient_role,
            title,
            content
        )
        create_audit_log(current_user.id, current_user.username, 'Secret Shared', f'Shared secret to {recipient_role}')
        flash('Secret shared successfully.', 'success')
    else:
        flash('Please fill in all fields.', 'error')
    return redirect(url_for('user.secrets'))


@user_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    # Allow users to set their currency display preference and bank account details
    if request.method == 'POST':
        mode = request.form.get('currency_display', 'both')
        bank_account_number = request.form.get('bank_account_number', '').strip()
        bank_ifsc = request.form.get('bank_ifsc', '').strip()
        bank_account_name = request.form.get('bank_account_name', '').strip()
        upi_id = request.form.get('upi_id', '').strip()
        
        try:
            if current_user.is_authenticated:
                set_user_currency(current_user.id, mode)
                set_user_bank_details(current_user.id, bank_account_number, bank_ifsc, bank_account_name, upi_id)
        except Exception as e:
            flash(f'Error updating account: {str(e)}', 'error')
            pass
        
        resp = make_response(redirect(url_for('user.account')))
        resp.set_cookie('currency_display', mode, max_age=30*24*3600)
        flash('Account preferences updated.', 'success')
        return resp

    # GET
    user_doc = get_user_by_id(current_user.id)
    pref = getattr(user_doc, 'currency_display', None) or get_user_currency(current_user.id)
    bank_details = get_user_bank_details(current_user.id)
    return render_template('user/account.html', pref=pref, bank_details=bank_details)
