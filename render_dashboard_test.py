import traceback
from app import app

try:
    with app.app_context(), app.test_request_context('/'):
        t = app.jinja_env.get_template('user/dashboard.html')
        class Stats:
            pass
        class DummyUser:
            is_authenticated = False
        stats = Stats()
        stats.total_spent = 123.45
        stats.total_revenue = 678.9
        stats.total_payments = 5
        stats.complaints_by_status = {'Pending':1,'In Review':0,'Resolved':0}
        out = t.render(stats=stats, currency_display='both', current_user=DummyUser())
        print('RENDER_OK')
        print(out[:800])
except Exception:
    traceback.print_exc()
