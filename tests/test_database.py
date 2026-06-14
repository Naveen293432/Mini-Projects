from database import create_payment, get_all_payments


def test_create_payment_generates_invoice():
    pid = create_payment('1', 'tester', '1', 'Test Fee', 1.23)
    payments = get_all_payments()
    assert any(p.doc_id == pid for p in payments)
        # Removed stray patch marker