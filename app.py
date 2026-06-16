import os
import logging
from urllib.parse import urlparse
from flask import Flask
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix

logging.basicConfig(level=logging.DEBUG)


def _load_project_env_bat():
    """Load simple KEY=VALUE entries from .env.bat for local development."""
    env_bat_path = os.path.join(os.path.dirname(__file__), '.env.bat')
    if not os.path.exists(env_bat_path):
        return

    try:
        with open(env_bat_path, 'r', encoding='utf-8-sig') as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith('REM') or line.startswith('::'):
                    continue
                if line.lower().startswith('@echo'):
                    continue
                if not line.upper().startswith('SET '):
                    continue

                body = line[4:].strip()
                if '=' not in body:
                    continue
                key, value = body.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"')
                if key:
                    os.environ[key] = value
    except Exception:
        logging.exception('Failed to read .env.bat')


# Only load local .env.bat during local development
if os.path.exists('.env.bat'):
    try:
        _load_project_env_bat()
    except Exception:
        logging.exception("Failed to load .env.bat")

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET","secret")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024


def _normalize_algorand_address(receiver):
    raw = (receiver or '').strip()
    if not raw:
        return ''

    candidate = raw
    if '://' in raw:
        parsed = urlparse(raw)
        candidate = (parsed.path or '').lstrip('/') or (parsed.netloc or '')

    candidate = (candidate or '').split('?', 1)[0].split('#', 1)[0].strip().upper()
    return candidate


def _is_valid_algorand_address(address):
    if not address:
        return False
    try:
        from algosdk import encoding as algo_encoding
        return bool(algo_encoding.is_valid_address(address))
    except Exception:
        # Fallback structural check when SDK import fails.
        return len(address) == 58 and address.isalnum()


def _validate_algorand_receiver_config():
    strict = os.environ.get('ALGORAND_CONFIG_STRICT', 'false').lower() in ('1', 'true', 'yes')
    raw_receiver = os.environ.get('ALGORAND_RECEIVER_ADDRESS', '')
    normalized_receiver = _normalize_algorand_address(raw_receiver)
    is_valid = _is_valid_algorand_address(normalized_receiver)

    if is_valid:
        if normalized_receiver != (raw_receiver or '').strip():
            logging.warning(
                'ALGORAND_RECEIVER_ADDRESS normalized from "%s" to "%s"',
                raw_receiver,
                normalized_receiver,
            )
        os.environ['ALGORAND_RECEIVER_ADDRESS'] = normalized_receiver
        return

    msg = (
        'Invalid or missing ALGORAND_RECEIVER_ADDRESS. Invoice QR and Algorand URI generation will fail. '
        'Set a valid 58-char Algorand address and restart the app. '
        'You can verify current status at /admin/chain/config after login as administrator.'
    )
    if strict:
        raise RuntimeError(msg)
    logging.error(msg)


_validate_algorand_receiver_config()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# register currency filter (log failures and provide a safe fallback)
try:
    from utils.currency import usd_to_inr
except Exception:
    logging.exception('Failed to import utils.currency.usd_to_inr; using fallback')
    def usd_to_inr(amount):
        try:
            return float(amount)
        except Exception:
            return amount

app.jinja_env.filters['to_inr'] = usd_to_inr

from database import get_user_by_id
from flask_login import current_user
from database import get_user_currency
from flask import request


@app.context_processor
def inject_currency_display():
    # Prefer authenticated user's stored preference, fallback to cookie
    try:
        if current_user and current_user.is_authenticated:
            mode = getattr(current_user, 'currency_display', None) or get_user_currency(current_user.id)
        else:
            mode = request.cookies.get('currency_display', 'both')
    except Exception:
        mode = request.cookies.get('currency_display', 'both')
    return dict(currency_display=mode)

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.dbmanager import dbmanager_bp
from routes.user import user_bp
from routes.main import main_bp
from routes.webhook import webhook_bp

app.register_blueprint(main_bp)
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(dbmanager_bp, url_prefix='/dbmanager')
app.register_blueprint(user_bp, url_prefix='/user')
app.register_blueprint(webhook_bp, url_prefix='/webhook')

# Optionally start Algorand background worker in a daemon thread
if os.environ.get('START_ALGORAND_WORKER', 'false').lower() in ('1', 'true', 'yes'):
    try:
        import threading
        from algorand_worker import run_loop

        t = threading.Thread(target=run_loop, kwargs={'interval_seconds': int(os.environ.get('ALGORAND_WORKER_INTERVAL', '60'))})
        t.daemon = True
        t.start()
    except Exception:
        pass

# Optionally start file retry worker for cloud/blockchain sync recovery
if os.environ.get('START_FILE_RETRY_WORKER', 'false').lower() in ('1', 'true', 'yes'):
    try:
        import threading
        from file_retry_worker import run_loop as file_retry_loop

        t2 = threading.Thread(
            target=file_retry_loop,
            kwargs={'interval_seconds': int(os.environ.get('FILE_RETRY_INTERVAL', '180'))}
        )
        t2.daemon = True
        t2.start()
    except Exception:
        pass
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)