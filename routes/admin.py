from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
import os
from urllib.parse import urlparse
from database import (
    get_all_users, update_user, delete_user, approve_user,
    get_all_fees, create_fee, update_fee, delete_fee, get_fee_by_id,
    get_all_complaints, update_complaint,
    get_all_payments, get_all_audit_logs, get_all_files,
    create_secret, get_all_secrets, create_audit_log
)
from database import get_payment_by_id, update_payment, get_database_file_path
from cloud_storage import list_local_objects
import algorand
import algorand_server
from flask import send_file, make_response, request
import csv
import io
from file_retry_worker import run_once as run_file_retry_once

admin_bp = Blueprint('admin', __name__)


def _normalize_algorand_address(receiver):
    raw = (receiver or '').strip()
    if not raw:
        return ''

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
            return ''
    except Exception:
        # If SDK is unavailable, treat normalized candidate as best effort.
        pass

    return candidate


def _is_valid_algorand_address(address):
    if not address:
        return False
    try:
        from algosdk import encoding as algo_encoding
        return bool(algo_encoding.is_valid_address(address))
    except Exception:
        # Fallback structural check when SDK validation isn't available.
        return len(address) == 58 and address.isalnum()


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'administrator':
            flash('Access denied. Administrator privileges required.', 'error')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    users = get_all_users()
    complaints = get_all_complaints()
    payments = get_all_payments()
    pending_users = [u for u in users if u.role == 'user' and not getattr(u, 'approved', True)]
    
    stats = {
        'total_users': len(users),
        'pending_users': len(pending_users),
        'pending_complaints': len([c for c in complaints if c.get('status') == 'Pending']),
        'total_payments': len(payments),
        'total_revenue': sum(p.get('amount', 0) for p in payments)
    }
    return render_template(
        'admin/dashboard.html',
        stats=stats,
        db_path=get_database_file_path(),
        cloud_root=os.path.abspath(os.environ.get('CLOUD_LOCAL_ROOT', os.path.join('data', 'cloud_storage'))),
        file_records=get_all_files(),
        cloud_objects=list_local_objects(os.path.abspath(os.environ.get('CLOUD_LOCAL_ROOT', os.path.join('data', 'cloud_storage')))),
    )


@admin_bp.route('/users')
@login_required
@admin_required
def user_management():
    users = get_all_users()
    view = request.args.get('status', '').strip().lower()
    if view == 'pending':
        users = [u for u in users if u.role == 'user' and not getattr(u, 'approved', True)]
    return render_template('admin/users.html', users=users, view=view)


@admin_bp.route('/users/<user_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_user(user_id):
    role = request.form.get('role')
    if role in ['administrator', 'dbmanager', 'user']:
        update_user(user_id, {'role': role})
        create_audit_log(current_user.id, current_user.username, 'User Update', f'Updated user {user_id} role to {role}')
        flash('User updated successfully.', 'success')
    return redirect(url_for('admin.user_management'))


@admin_bp.route('/users/<user_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_user_route(user_id):
    approve_user(user_id)
    create_audit_log(current_user.id, current_user.username, 'User Approval', f'Approved user {user_id}')
    flash('User approved successfully.', 'success')
    return redirect(url_for('admin.user_management'))


@admin_bp.route('/users/<user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user_route(user_id):
    if user_id != current_user.id:
        delete_user(user_id)
        create_audit_log(current_user.id, current_user.username, 'User Delete', f'Deleted user {user_id}')
        flash('User deleted successfully.', 'success')
    else:
        flash('Cannot delete your own account.', 'error')
    return redirect(url_for('admin.user_management'))


@admin_bp.route('/fees')
@login_required
@admin_required
def fee_configuration():
    fees = get_all_fees()
    return render_template('admin/fees.html', fees=fees)


@admin_bp.route('/fees/create', methods=['POST'])
@login_required
@admin_required
def create_fee_route():
    name = request.form.get('name', '').strip()
    amount = float(request.form.get('amount', 0))
    description = request.form.get('description', '').strip()
    due_date = request.form.get('due_date', '')
    
    if name and amount > 0:
        create_fee(name, amount, description, due_date, current_user.username)
        create_audit_log(current_user.id, current_user.username, 'Fee Created', f'Created fee: {name}')
        flash('Fee created successfully.', 'success')
    else:
        flash('Please provide valid fee details.', 'error')
    return redirect(url_for('admin.fee_configuration'))


@admin_bp.route('/fees/<fee_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_fee(fee_id):
    name = request.form.get('name', '').strip()
    amount = float(request.form.get('amount', 0))
    description = request.form.get('description', '').strip()
    due_date = request.form.get('due_date', '')
    
    if name and amount > 0:
        update_fee(fee_id, {
            'name': name,
            'amount': amount,
            'description': description,
            'due_date': due_date
        })
        create_audit_log(current_user.id, current_user.username, 'Fee Updated', f'Updated fee: {name}')
        flash('Fee updated successfully.', 'success')
    return redirect(url_for('admin.fee_configuration'))


@admin_bp.route('/fees/<fee_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_fee_route(fee_id):
    delete_fee(fee_id)
    create_audit_log(current_user.id, current_user.username, 'Fee Deleted', f'Deleted fee {fee_id}')
    flash('Fee deleted successfully.', 'success')
    return redirect(url_for('admin.fee_configuration'))


@admin_bp.route('/complaints')
@login_required
@admin_required
def complaint_review():
    complaints = get_all_complaints()
    return render_template('admin/complaints.html', complaints=complaints)


@admin_bp.route('/complaints/<complaint_id>/update', methods=['POST'])
@login_required
@admin_required
def update_complaint_route(complaint_id):
    status = request.form.get('status')
    response = request.form.get('response', '').strip()
    
    if status in ['Pending', 'In Review', 'Resolved']:
        update_complaint(complaint_id, {
            'status': status,
            'admin_response': response
        })
        create_audit_log(current_user.id, current_user.username, 'Complaint Updated', f'Updated complaint {complaint_id} status to {status}')
        flash('Complaint updated successfully.', 'success')
    return redirect(url_for('admin.complaint_review'))


@admin_bp.route('/reports')
@login_required
@admin_required
def system_reports():
    users = get_all_users()
    payments = get_all_payments()
    complaints = get_all_complaints()
    
    stats = {
        'users_by_role': {
            'administrator': len([u for u in users if u.role == 'administrator']),
            'dbmanager': len([u for u in users if u.role == 'dbmanager']),
            'user': len([u for u in users if u.role == 'user'])
        },
        'complaints_by_status': {
            'Pending': len([c for c in complaints if c.get('status') == 'Pending']),
            'In Review': len([c for c in complaints if c.get('status') == 'In Review']),
            'Resolved': len([c for c in complaints if c.get('status') == 'Resolved'])
        },
        'total_revenue': sum(p.get('amount', 0) for p in payments),
        'total_payments': len(payments)
    }
    return render_template('admin/reports.html', stats=stats)


@admin_bp.route('/chain')
@login_required
@admin_required
def chain_view():
    payments = get_all_payments()
    blockchain_records = [
        p for p in payments
        if p.get('algorand_tx_id') or p.get('algorand_status')
    ]
    return render_template('admin/algorand.html', payments=payments, blockchain_records=blockchain_records)


@admin_bp.route('/chain/config')
@login_required
@admin_required
def chain_config():
    raw_receiver = os.environ.get('ALGORAND_RECEIVER_ADDRESS', '')
    normalized_receiver = _normalize_algorand_address(raw_receiver)
    is_valid = _is_valid_algorand_address(normalized_receiver)
    sample_invoice = 'sample-invoice-id'
    sample_amount_microalgo = 1000000
    sample_uri = ''
    if normalized_receiver and is_valid:
        sample_uri = f'algorand://{normalized_receiver}?amount={sample_amount_microalgo}&note={sample_invoice}'

    return render_template(
        'admin/chain_config.html',
        raw_receiver=raw_receiver,
        normalized_receiver=normalized_receiver,
        is_valid=is_valid,
        sample_uri=sample_uri,
    )


@admin_bp.route('/chain/verify/<payment_id>', methods=['POST'])
@login_required
@admin_required
def chain_verify(payment_id):
    payment = get_payment_by_id(payment_id)
    if not payment or not payment.get('algorand_tx_id'):
        flash('Payment or tx id not found.', 'error')
        return redirect(url_for('admin.chain_view'))

    res = algorand.verify_transaction(payment.get('algorand_tx_id'))
    status = 'Pending'
    if res.get('confirmed'):
        status = 'Confirmed'
    elif res.get('error'):
        status = 'Error: ' + str(res.get('error'))

    update_payment(payment_id, {'algorand_status': status})
    flash('Transaction verification complete.', 'success')
    return redirect(url_for('admin.chain_view'))


@admin_bp.route('/chain/export')
@login_required
@admin_required
def chain_export():
    # honor same filters as chain_view
    q = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    payments = get_all_payments()
    if q:
        payments = [p for p in payments if q.lower() in (str(p.get('user_name', '')).lower() + ' ' + str(p.get('fee_name', '')).lower() + ' ' + str(p.get('algorand_tx_id') or '').lower())]
    if status:
        payments = [p for p in payments if (p.get('algorand_status') or '').lower() == status.lower()]
    
    output = io.StringIO()
    writer = csv.writer(output)
    # Include USD and INR amounts and note the admin's display preference
    pref = 'both'
    try:
        pref = getattr(current_user, 'currency_display', None) or request.cookies.get('currency_display', 'both')
    except Exception:
        pref = request.cookies.get('currency_display', 'both')

    writer.writerow(['payment_id', 'user_id', 'fee_name', 'amount_usd', 'amount_inr', 'display_amount', 'currency_pref', 'algorand_tx_id', 'algorand_status', 'created_at'])
    for p in payments:
        usd = p.get('amount')
        try:
            inr = float(usd) * float( ( (os.environ.get('FIXED_USD_TO_INR') or '82.0') ))
        except Exception:
            inr = float(usd)
        if pref == 'usd':
            display = f"${usd:.2f}"
        elif pref == 'inr':
            display = f"₹{inr:.2f}"
        else:
            display = f"${usd:.2f} / ₹{inr:.2f}"
        writer.writerow([p.doc_id, p.get('user_id'), p.get('fee_name'), f"{usd:.2f}", f"{inr:.2f}", display, pref, p.get('algorand_tx_id'), p.get('algorand_status'), p.get('created_at')])
    output.seek(0)
    resp = make_response(output.read())
    resp.headers['Content-Disposition'] = 'attachment; filename=algorand_payments.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp


@admin_bp.route('/audit-logs')
@login_required
@admin_required
def audit_logs():
    logs = get_all_audit_logs()
    logs = sorted(logs, key=lambda x: x.get('created_at', ''), reverse=True)
    return render_template('admin/audit_logs.html', logs=logs)


@admin_bp.route('/secrets')
@login_required
@admin_required
def secrets():
    all_secrets = get_all_secrets()
    return render_template('admin/secrets.html', secrets=all_secrets)


@admin_bp.route('/secrets/share', methods=['POST'])
@login_required
@admin_required
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
    return redirect(url_for('admin.secrets'))

@admin_bp.route('/chain/send/<payment_id>', methods=['POST'])
@login_required
@admin_required
def chain_send(payment_id):
    payment = get_payment_by_id(payment_id)
    to_address = request.form.get('to_address')
    if not payment or not to_address:
        flash('Payment or destination address missing.', 'error')
        return redirect(url_for('admin.chain_view'))

    amount = float(payment.get('amount', 0))
    try:
        txid = algorand_server.send_payment(to_address, amount)
        # record server-sent tx id
        update_payment(payment_id, {'algorand_tx_id': txid, 'algorand_status': 'Server-Sent'})
        flash(f'Sent {amount} ALGO to {to_address}. txid: {txid}', 'success')
    except Exception as e:
        flash(f'Failed to send: {str(e)}', 'error')
    return redirect(url_for('admin.chain_view'))


@admin_bp.route('/system/storage')
@login_required
@admin_required
def storage_health():
    db_path = get_database_file_path()
    db_exists = os.path.exists(db_path)
    upload_root = os.path.abspath('uploads')
    cloud_root = os.path.abspath(os.environ.get('CLOUD_LOCAL_ROOT', os.path.join('data', 'cloud_storage')))

    files = get_all_files()
    cloud_objects = list_local_objects(cloud_root)
    blockchain_records = [
        f for f in files
        if f.get('blockchain_tx_id') or f.get('blockchain_status')
    ]
    cloud_failed = [
        f for f in files
        if str(f.get('cloud_status') or '').lower().startswith('error')
    ]
    chain_failed = [
        f for f in files
        if str(f.get('blockchain_status') or '').lower() in ('failed',) or str(f.get('blockchain_status') or '').lower().startswith('error')
    ]

    return render_template(
        'admin/storage_health.html',
        db_path=db_path,
        db_exists=db_exists,
        upload_root=upload_root,
        cloud_root=cloud_root,
        cloud_provider=os.environ.get('CLOUD_PROVIDER', 'local'),
        total_files=len(files),
        file_records=files,
        cloud_objects=cloud_objects,
        blockchain_records=blockchain_records,
        cloud_failed_count=len(cloud_failed),
        chain_failed_count=len(chain_failed),
        retry_worker_enabled=os.environ.get('START_FILE_RETRY_WORKER', 'false').lower() in ('1', 'true', 'yes'),
    )


@admin_bp.route('/system/storage/retry-now', methods=['POST'])
@login_required
@admin_required
def storage_retry_now():
    try:
        summary = run_file_retry_once()
        flash(
            'Retry run complete: scanned={scanned}, updated={updated}, cloud_retried={cloud_retried}, chain_retried={chain_retried}'.format(**summary),
            'success'
        )
    except Exception as e:
        flash(f'Retry run failed: {str(e)}', 'error')
    return redirect(url_for('admin.storage_health'))
