from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from database import create_user, get_user_by_username, get_user_by_email, create_audit_log, store_user_keys
from encryption import generate_rsa_keypair

auth_bp = Blueprint('auth', __name__)

LOGIN_TARGETS = {
    'user': 'user.dashboard',
    'administrator': 'admin.dashboard',
    'dbmanager': 'dbmanager.dashboard'
}

LOGIN_LABELS = {
    'user': 'User Portal',
    'administrator': 'Administrator Portal',
    'dbmanager': 'Database Manager Portal'
}


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = 'user'
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        
        if not username or not email or not password:
            flash('Please fill in all required fields.', 'error')
            return render_template('auth/signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/signup.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('auth/signup.html')
        
        if get_user_by_username(username):
            flash('Username already exists.', 'error')
            return render_template('auth/signup.html')
        
        if get_user_by_email(email):
            flash('Email already registered.', 'error')
            return render_template('auth/signup.html')
        
        user_id = create_user(username, email, password, role, full_name, phone, address)
        
        public_key, private_key = generate_rsa_keypair()
        store_user_keys(str(user_id), public_key, private_key)
        
        create_audit_log(str(user_id), username, 'User Registration', f'New {role} account created and pending approval')
        
        flash('Account created successfully! Your account is waiting for administrator approval.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/signup.html')


@auth_bp.route('/login', defaults={'role': None}, methods=['GET'])
@auth_bp.route('/login/<role>', methods=['GET', 'POST'])
def login(role):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if role and role not in LOGIN_TARGETS:
        flash('Invalid login portal.', 'error')
        return redirect(url_for('auth.login'))

    if role is None:
        role = 'user'
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Please enter username and password.', 'error')
            return render_template('auth/login.html', login_role=role, login_label=LOGIN_LABELS.get(role, 'Login'), show_role_switcher=True)
        
        user = get_user_by_username(username)
        
        if user and user.check_password(password):
            if user.role != role:
                flash('This account does not match the selected login portal.', 'error')
                return render_template('auth/login.html', login_role=role, login_label=LOGIN_LABELS.get(role, 'Login'), show_role_switcher=True)

            if user.role == 'user' and not getattr(user, 'approved', True):
                flash('Your account is pending administrator approval.', 'error')
                return render_template('auth/login.html', login_role=role, login_label=LOGIN_LABELS.get(role, 'Login'), show_role_switcher=True)

            login_user(user)
            create_audit_log(user.id, user.username, 'Login', f'{user.role} logged in through {role} portal')

            return redirect(url_for(LOGIN_TARGETS[user.role]))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('auth/login.html', login_role=role, login_label=LOGIN_LABELS.get(role, 'Login'), show_role_switcher=True)


@auth_bp.route('/logout')
@login_required
def logout():
    create_audit_log(current_user.id, current_user.username, 'Logout', f'{current_user.role} logged out')
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.index'))
