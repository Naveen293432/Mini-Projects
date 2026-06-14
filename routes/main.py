import os

from flask import Blueprint, render_template, redirect, url_for, request, make_response
from flask_login import current_user
from database import set_user_currency, get_database_file_path
from flask_login import current_user

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'administrator':
            return redirect(url_for('admin.dashboard'))
        elif current_user.role == 'dbmanager':
            return redirect(url_for('dbmanager.dashboard'))
        else:
            return redirect(url_for('user.dashboard'))
    return render_template(
        'index.html',
        db_path=get_database_file_path(),
        uploads_root=os.path.abspath('uploads'),
        encrypted_root=os.path.abspath(os.path.join('uploads', 'encrypted')),
        decrypted_root=os.path.abspath(os.path.join('uploads', 'decrypted')),
        cloud_root=os.path.abspath(os.environ.get('CLOUD_LOCAL_ROOT', os.path.join('data', 'cloud_storage'))),
    )


@main_bp.route('/set_currency/<mode>')
def set_currency(mode):
    if mode not in ('usd', 'inr', 'both'):
        mode = 'both'
    # Persist for authenticated users
    if current_user and current_user.is_authenticated:
        try:
            set_user_currency(current_user.id, mode)
        except Exception:
            pass

    resp = make_response(redirect(request.referrer or url_for('main.index')))
    resp.set_cookie('currency_display', mode, max_age=30*24*3600)
    return resp
