import os
import hashlib
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
from functools import wraps
from werkzeug.utils import secure_filename
from database import (
    get_all_files, get_file_by_id, create_file_record, delete_file_record,
    get_all_maintenance, create_maintenance, update_maintenance,
    get_all_users, get_all_payments, get_all_complaints,
    create_secret, get_secrets_for_role, get_all_secrets,
    create_audit_log, get_user_keys
)
from encryption import encrypt_file_hybrid, decrypt_file_hybrid, generate_rsa_keypair
from cloud_storage import upload_bytes
from cloud_storage import list_local_objects
import algorand

dbmanager_bp = Blueprint('dbmanager', __name__)


def dbmanager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'dbmanager':
            flash('Access denied. Database Management privileges required.', 'error')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


@dbmanager_bp.route('/dashboard')
@login_required
@dbmanager_required
def dashboard():
    files = get_all_files()
    maintenance = get_all_maintenance()
    users = get_all_users()
    
    stats = {
        'total_files': len(files),
        'encrypted_files': len([f for f in files if f.get('encrypted')]),
        'scheduled_maintenance': len([m for m in maintenance if m.get('status') == 'Scheduled']),
        'total_users': len(users)
    }
    return render_template(
        'dbmanager/dashboard.html',
        stats=stats,
        db_path=os.path.abspath(os.path.join('data', 'database.json')),
        cloud_root=os.path.abspath(os.environ.get('CLOUD_LOCAL_ROOT', os.path.join('data', 'cloud_storage'))),
        file_records=files,
        cloud_objects=list_local_objects(os.path.abspath(os.environ.get('CLOUD_LOCAL_ROOT', os.path.join('data', 'cloud_storage')))),
    )


@dbmanager_bp.route('/monitoring')
@login_required
@dbmanager_required
def db_monitoring():
    files = get_all_files()
    users = get_all_users()
    payments = get_all_payments()
    
    stats = {
        'total_storage': sum(f.get('file_size', 0) for f in files),
        'total_files': len(files),
        'total_users': len(users),
        'total_transactions': len(payments)
    }
    return render_template('dbmanager/monitoring.html', stats=stats)


@dbmanager_bp.route('/files')
@login_required
@dbmanager_required
def file_management():
    files = get_all_files()
    return render_template('dbmanager/files.html', files=files)


@dbmanager_bp.route('/files/upload', methods=['POST'])
@login_required
@dbmanager_required
def upload_file():
    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('dbmanager.file_management'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('dbmanager.file_management'))
    
    if file:
        original_filename = secure_filename(file.filename)
        file_data = file.read()
        file_size = len(file_data)
        
        encrypt_option = request.form.get('encrypt', 'no')
        
        if encrypt_option == 'yes':
            keys = get_user_keys(current_user.id)
            if not keys:
                public_key, private_key = generate_rsa_keypair()
                from database import store_user_keys
                store_user_keys(current_user.id, public_key, private_key)
                keys = {'public_key': public_key, 'private_key': private_key}
            
            encrypted_data = encrypt_file_hybrid(file_data, keys['public_key'])
            filename = f"encrypted_{current_user.id}_{original_filename}"
            filepath = os.path.join('uploads/encrypted', filename)
            
            with open(filepath, 'wb') as f:
                f.write(encrypted_data)

            file_hash = hashlib.sha256(encrypted_data).hexdigest()
            cloud_key = f"dbmanager/{current_user.id}/{filename}"
            cloud_result = upload_bytes(cloud_key, encrypted_data)
            chain_result = algorand.register_file_hash(file_hash, reference=filename)

            create_file_record(
                filename,
                original_filename,
                current_user.id,
                'dbmanager',
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
        else:
            filename = f"plain_{current_user.id}_{original_filename}"
            filepath = os.path.join('uploads/decrypted', filename)
            
            with open(filepath, 'wb') as f:
                f.write(file_data)

            file_hash = hashlib.sha256(file_data).hexdigest()
            cloud_key = f"dbmanager/{current_user.id}/{filename}"
            cloud_result = upload_bytes(cloud_key, file_data)
            chain_result = algorand.register_file_hash(file_hash, reference=filename)

            create_file_record(
                filename,
                original_filename,
                current_user.id,
                'dbmanager',
                False,
                file_size,
                file_hash=file_hash,
                cloud_provider=cloud_result.get('provider'),
                cloud_url=cloud_result.get('url'),
                cloud_status='Stored' if cloud_result.get('stored') else f"Error: {cloud_result.get('error')}",
                blockchain_tx_id=chain_result.get('txid'),
                blockchain_status=chain_result.get('status'),
            )
            create_audit_log(current_user.id, current_user.username, 'File Uploaded', f'Uploaded: {original_filename}')
        
        flash('File uploaded successfully.', 'success')
    
    return redirect(url_for('dbmanager.file_management'))


@dbmanager_bp.route('/files/<file_id>/download-encrypted')
@login_required
@dbmanager_required
def download_encrypted(file_id):
    file_record = get_file_by_id(file_id)
    if not file_record:
        flash('File not found.', 'error')
        return redirect(url_for('dbmanager.file_management'))
    
    filename = file_record.get('filename')
    if file_record.get('encrypted'):
        filepath = os.path.join('uploads/encrypted', filename)
    else:
        filepath = os.path.join('uploads/decrypted', filename)
    
    if os.path.exists(filepath):
        create_audit_log(current_user.id, current_user.username, 'File Downloaded', f'Downloaded encrypted: {filename}')
        return send_file(filepath, as_attachment=True, download_name=f"encrypted_{file_record.get('original_filename')}")
    
    flash('File not found on server.', 'error')
    return redirect(url_for('dbmanager.file_management'))


@dbmanager_bp.route('/files/<file_id>/download-decrypted')
@login_required
@dbmanager_required
def download_decrypted(file_id):
    file_record = get_file_by_id(file_id)
    if not file_record:
        flash('File not found.', 'error')
        return redirect(url_for('dbmanager.file_management'))
    
    filename = file_record.get('filename')
    
    if file_record.get('encrypted'):
        filepath = os.path.join('uploads/encrypted', filename)
        
        if not os.path.exists(filepath):
            flash('File not found on server.', 'error')
            return redirect(url_for('dbmanager.file_management'))
        
        owner_id = file_record.get('owner_id')
        keys = get_user_keys(str(owner_id))
        
        if not keys:
            flash('Encryption keys not found.', 'error')
            return redirect(url_for('dbmanager.file_management'))
        
        with open(filepath, 'rb') as f:
            encrypted_data = f.read()
        
        try:
            decrypted_data = decrypt_file_hybrid(encrypted_data, keys['private_key'])
            
            temp_filepath = os.path.join('uploads/decrypted', f"temp_{file_record.get('original_filename')}")
            with open(temp_filepath, 'wb') as f:
                f.write(decrypted_data)
            
            create_audit_log(current_user.id, current_user.username, 'File Decrypted', f'Downloaded decrypted: {filename}')
            
            response = send_file(temp_filepath, as_attachment=True, download_name=file_record.get('original_filename'))
            return response
        except Exception as e:
            flash(f'Decryption failed: {str(e)}', 'error')
            return redirect(url_for('dbmanager.file_management'))
    else:
        filepath = os.path.join('uploads/decrypted', filename)
        if os.path.exists(filepath):
            create_audit_log(current_user.id, current_user.username, 'File Downloaded', f'Downloaded: {filename}')
            return send_file(filepath, as_attachment=True, download_name=file_record.get('original_filename'))
    
    flash('File not found on server.', 'error')
    return redirect(url_for('dbmanager.file_management'))


@dbmanager_bp.route('/encrypted-downloads')
@login_required
@dbmanager_required
def encrypted_downloads():
    files = get_all_files()
    encrypted_files = [f for f in files if f.get('encrypted')]
    return render_template('dbmanager/encrypted_downloads.html', files=encrypted_files)


@dbmanager_bp.route('/maintenance')
@login_required
@dbmanager_required
def maintenance_scheduling():
    maintenance = get_all_maintenance()
    return render_template('dbmanager/maintenance.html', maintenance=maintenance)


@dbmanager_bp.route('/maintenance/create', methods=['POST'])
@login_required
@dbmanager_required
def create_maintenance_route():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    scheduled_date = request.form.get('scheduled_date', '')
    
    if title and scheduled_date:
        create_maintenance(title, description, scheduled_date, current_user.username)
        create_audit_log(current_user.id, current_user.username, 'Maintenance Scheduled', f'Scheduled: {title}')
        flash('Maintenance scheduled successfully.', 'success')
    else:
        flash('Please fill in all required fields.', 'error')
    
    return redirect(url_for('dbmanager.maintenance_scheduling'))


@dbmanager_bp.route('/maintenance/<maintenance_id>/update', methods=['POST'])
@login_required
@dbmanager_required
def update_maintenance_route(maintenance_id):
    status = request.form.get('status')
    if status in ['Scheduled', 'In Progress', 'Completed', 'Cancelled']:
        update_maintenance(maintenance_id, {'status': status})
        create_audit_log(current_user.id, current_user.username, 'Maintenance Updated', f'Updated maintenance {maintenance_id} to {status}')
        flash('Maintenance updated successfully.', 'success')
    return redirect(url_for('dbmanager.maintenance_scheduling'))


@dbmanager_bp.route('/analytics')
@login_required
@dbmanager_required
def performance_analytics():
    files = get_all_files()
    users = get_all_users()
    maintenance = get_all_maintenance()
    
    stats = {
        'files_by_type': {
            'encrypted': len([f for f in files if f.get('encrypted')]),
            'unencrypted': len([f for f in files if not f.get('encrypted')])
        },
        'storage_used': sum(f.get('file_size', 0) for f in files),
        'maintenance_stats': {
            'Scheduled': len([m for m in maintenance if m.get('status') == 'Scheduled']),
            'Completed': len([m for m in maintenance if m.get('status') == 'Completed']),
            'In Progress': len([m for m in maintenance if m.get('status') == 'In Progress'])
        }
    }
    return render_template('dbmanager/analytics.html', stats=stats)


@dbmanager_bp.route('/secrets')
@login_required
@dbmanager_required
def secrets():
    my_secrets = get_secrets_for_role('dbmanager')
    all_secrets = get_all_secrets()
    return render_template('dbmanager/secrets.html', my_secrets=my_secrets, all_secrets=all_secrets)


@dbmanager_bp.route('/secrets/share', methods=['POST'])
@login_required
@dbmanager_required
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
    return redirect(url_for('dbmanager.secrets'))
