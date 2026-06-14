import os
import time
import requests

# Cache
_CACHE = {'rate': None, 'ts': 0}
CACHE_TTL = int(os.environ.get('FX_CACHE_TTL', '300'))


def get_fixed_rate():
    v = os.environ.get('FIXED_USD_TO_INR')
    if v:
        try:
            return float(v)
        except Exception:
            return None
    return None


def fetch_live_rate():
    # Use exchangerate.host free API
    try:
        r = requests.get('https://api.exchangerate.host/latest?base=USD&symbols=INR', timeout=5)
        if r.status_code == 200:
            data = r.json()
            rate = data.get('rates', {}).get('INR')
            if rate:
                return float(rate)
    except Exception:
        return None
    return None


def get_usd_to_inr_rate():
    # 1) fixed env var
    fixed = get_fixed_rate()
    if fixed:
        return fixed

    # 2) cached live fetch
    now = time.time()
    if _CACHE['rate'] and (now - _CACHE['ts'] < CACHE_TTL):
        return _CACHE['rate']

    rate = fetch_live_rate()
    if rate:
        _CACHE['rate'] = rate
        _CACHE['ts'] = now
        return rate

    # 3) fallback
    try:
        return float(os.environ.get('DEFAULT_USD_TO_INR', '82.0'))
    except Exception:
        return 82.0


def usd_to_inr(amount):
    try:
        rate = get_usd_to_inr_rate()
        return float(amount) * float(rate)
    except Exception:
        return amount * 82.0


def inr_to_usd(amount):
    try:
        rate = get_usd_to_inr_rate()
        return float(amount) / float(rate)
    except Exception:
        return float(amount) / 82.0


# ALGO conversion functions
_ALGO_CACHE = {'rate': None, 'ts': 0}
ALGO_CACHE_TTL = int(os.environ.get('FX_CACHE_TTL', '300'))


def get_fixed_algo_rate():
    """Get fixed USD to ALGO rate from environment"""
    v = os.environ.get('FIXED_USD_TO_ALGO')
    if v:
        try:
            return float(v)
        except Exception:
            return None
    return None


def fetch_live_algo_rate():
    """Fetch live USD to ALGO rate from API"""
    try:
        r = requests.get('https://api.exchangerate.host/latest?base=USD&symbols=USD', timeout=5)
        if r.status_code == 200:
            data = r.json()
            # For demo purposes, use a reasonable ALGO price (1 ALGO ≈ 0.20-0.30 USD)
            # In production, fetch from a crypto API like CoinGecko
            algo_price = 0.25  # Default ALGO price
            fixed = os.environ.get('ALGO_PRICE_USD')
            if fixed:
                try:
                    algo_price = float(fixed)
                except Exception:
                    pass
            return algo_price
    except Exception:
        return None
    return None


def get_usd_to_algo_rate():
    """Get USD to ALGO conversion rate"""
    # 1) fixed env var
    fixed = get_fixed_algo_rate()
    if fixed:
        return fixed

    # 2) cached live fetch
    now = time.time()
    if _ALGO_CACHE['rate'] and (now - _ALGO_CACHE['ts'] < ALGO_CACHE_TTL):
        return _ALGO_CACHE['rate']

    rate = fetch_live_algo_rate()
    if rate:
        _ALGO_CACHE['rate'] = rate
        _ALGO_CACHE['ts'] = now
        return rate

    # 3) fallback
    try:
        return float(os.environ.get('DEFAULT_USD_TO_ALGO', '0.25'))
    except Exception:
        return 0.25


def usd_to_algo(amount):
    """Convert USD amount to ALGO amount"""
    try:
        rate = get_usd_to_algo_rate()
        return float(amount) / float(rate)
    except Exception:
        return float(amount) / 0.25


def algo_to_microalgo(algo_amount):
    """Convert ALGO to microALGO (1 ALGO = 1,000,000 microALGO)"""
    try:
        return int(float(algo_amount) * 1_000_000)
    except Exception:
        return 0


def format_currency(amount, currency='usd'):
    """Format currency amount with proper precision"""
    try:
        if currency.lower() == 'usd':
            return f"${float(amount):.2f}"
        elif currency.lower() == 'inr':
            return f"₹{float(amount):.2f}"
        elif currency.lower() == 'algo':
            return f"{float(amount):.6f} ALGO"
        else:
            return f"{float(amount):.2f}"
    except Exception:
        return str(amount)
