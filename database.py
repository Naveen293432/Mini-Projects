import os
from datetime import datetime
import uuid
from tinydb import TinyDB, Query
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

DATA_DIR = os.environ.get('DATA_DIR', 'data')
DB_FILE_PATH = os.path.join(DATA_DIR, 'database.json')

os.makedirs(DATA_DIR, exist_ok=True)

db = TinyDB(DB_FILE_PATH)
users_table = db.table('users')
files_table = db.table('files')
complaints_table = db.table('complaints')
fees_table = db.table('fees')
payments_table = db.table('payments')
secrets_table = db.table('secrets')
audit_logs_table = db.table('audit_logs')
maintenance_table = db.table('maintenance')
keys_table = db.table('keys')

User = Query()
File = Query()
Complaint = Query()
Fee = Query()
Payment = Query()
Secret = Query()
AuditLog = Query()
Maintenance = Query()
Key = Query()


class UserModel(UserMixin):
    def __init__(self, doc_id, username, email, password_hash, role, full_name, phone, address, created_at, currency_display='both', approved=True):
        self.id = str(doc_id)
        self.doc_id = doc_id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.role = role
        self.full_name = full_name
        self.phone = phone
        self.address = address
        self.created_at = created_at
        self.currency_display = currency_display
        self.approved = approved

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def from_doc(doc):
        if doc is None:
            return None
        return UserModel(
            doc_id=doc.doc_id,
            username=doc.get('username'),
            email=doc.get('email'),
            password_hash=doc.get('password_hash'),
            role=doc.get('role'),
            full_name=doc.get('full_name', ''),
            phone=doc.get('phone', ''),
            address=doc.get('address', ''),
            created_at=doc.get('created_at', ''),
            currency_display=doc.get('currency_display', 'both'),
            approved=doc.get('approved', True)
        )


def create_user(username, email, password, role, full_name, phone, address, approved=None):
    password_hash = generate_password_hash(password)
    if approved is None:
        approved = role in ('administrator', 'dbmanager')
    doc_id = users_table.insert({
        'username': username,
        'email': email,
        'password_hash': password_hash,
        'role': role,
        'full_name': full_name,
        'phone': phone,
        'address': address,
        'currency_display': 'both',
        'approved': approved,
        'created_at': datetime.now().isoformat()
    })
    return doc_id


def set_user_currency(user_id, mode):
    if mode not in ('usd', 'inr', 'both'):
        mode = 'both'
    users_table.update({'currency_display': mode}, doc_ids=[int(user_id)])


def get_user_currency(user_id):
    doc = users_table.get(doc_id=int(user_id))
    if doc:
        return doc.get('currency_display', 'both')
    return 'both'


def get_user_by_username(username):
    docs = users_table.search(User.username == username)
    if docs:
        doc = docs[0]
        doc.doc_id = users_table.search(User.username == username)[0].doc_id
        return UserModel.from_doc(doc)
    return None


def get_user_by_email(email):
    docs = users_table.search(User.email == email)
    if docs:
        doc = docs[0]
        doc.doc_id = users_table.search(User.email == email)[0].doc_id
        return UserModel.from_doc(doc)
    return None


def get_user_by_id(user_id):
    doc = users_table.get(doc_id=int(user_id))
    if doc:
        doc.doc_id = int(user_id)
        return UserModel.from_doc(doc)
    return None


def get_all_users():
    docs = users_table.all()
    users = []
    for doc in docs:
        doc.doc_id = doc.doc_id
        users.append(UserModel.from_doc(doc))
    return users


def update_user(user_id, data):
    users_table.update(data, doc_ids=[int(user_id)])


def approve_user(user_id):
    users_table.update({'approved': True}, doc_ids=[int(user_id)])


def delete_user(user_id):
    users_table.remove(doc_ids=[int(user_id)])


def create_file_record(
    filename,
    original_filename,
    owner_id,
    owner_role,
    encrypted,
    file_size,
    file_hash=None,
    cloud_provider=None,
    cloud_url=None,
    cloud_status=None,
    blockchain_tx_id=None,
    blockchain_status=None,
):
    doc_id = files_table.insert({
        'filename': filename,
        'original_filename': original_filename,
        'owner_id': owner_id,
        'owner_role': owner_role,
        'encrypted': encrypted,
        'file_size': file_size,
        'file_hash': file_hash,
        'cloud_provider': cloud_provider,
        'cloud_url': cloud_url,
        'cloud_status': cloud_status,
        'blockchain_tx_id': blockchain_tx_id,
        'blockchain_status': blockchain_status,
        'shared_with': [],
        'created_at': datetime.now().isoformat()
    })
    return doc_id


def get_database_file_path():
    return os.path.abspath(DB_FILE_PATH)


def get_files_by_owner(owner_id):
    return files_table.search(File.owner_id == owner_id)


def get_all_files():
    return files_table.all()


def get_file_by_id(file_id):
    return files_table.get(doc_id=int(file_id))


def update_file(file_id, data):
    files_table.update(data, doc_ids=[int(file_id)])


def delete_file_record(file_id):
    files_table.remove(doc_ids=[int(file_id)])


def create_complaint(user_id, user_name, category, priority, subject, description):
    doc_id = complaints_table.insert({
        'user_id': user_id,
        'user_name': user_name,
        'category': category,
        'priority': priority,
        'subject': subject,
        'description': description,
        'status': 'Pending',
        'admin_response': '',
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat()
    })
    return doc_id


def get_complaints_by_user(user_id):
    return complaints_table.search(Complaint.user_id == user_id)


def get_all_complaints():
    return complaints_table.all()


def update_complaint(complaint_id, data):
    data['updated_at'] = datetime.now().isoformat()
    complaints_table.update(data, doc_ids=[int(complaint_id)])


def create_fee(name, amount, description, due_date, created_by):
    doc_id = fees_table.insert({
        'name': name,
        'amount': amount,
        'description': description,
        'due_date': due_date,
        'created_by': created_by,
        'created_at': datetime.now().isoformat()
    })
    return doc_id


def get_all_fees():
    return fees_table.all()


def get_fee_by_id(fee_id):
    return fees_table.get(doc_id=int(fee_id))


def update_fee(fee_id, data):
    fees_table.update(data, doc_ids=[int(fee_id)])


def delete_fee(fee_id):
    fees_table.remove(doc_ids=[int(fee_id)])


def create_payment(user_id, user_name, fee_id, fee_name, amount, algorand_tx_id=None, paid_currency='usd'):
    # Create a payment record. Generate an invoice id to help match on-chain notes.
    invoice_id = uuid.uuid4().hex
    alg_status = 'Not Applicable'
    status = 'Completed'
    if not algorand_tx_id:
        alg_status = 'Awaiting Payment'
        status = 'Pending'

    doc_id = payments_table.insert({
        'user_id': user_id,
        'user_name': user_name,
        'fee_id': fee_id,
        'fee_name': fee_name,
        'amount': amount,
        'paid_currency': paid_currency,
        'status': status,
        'invoice_id': invoice_id,
        'algorand_tx_id': algorand_tx_id,
        'algorand_status': alg_status,
        'created_at': datetime.now().isoformat()
    })
    return doc_id


def get_payments_by_user(user_id):
    return payments_table.search(Payment.user_id == user_id)


def get_all_payments():
    return payments_table.all()


def get_payment_by_id(payment_id):
    return payments_table.get(doc_id=int(payment_id))


def update_payment(payment_id, data):
    data['updated_at'] = datetime.now().isoformat()
    payments_table.update(data, doc_ids=[int(payment_id)])


def create_secret(sender_id, sender_name, sender_role, recipient_role, title, content):
    doc_id = secrets_table.insert({
        'sender_id': sender_id,
        'sender_name': sender_name,
        'sender_role': sender_role,
        'recipient_role': recipient_role,
        'title': title,
        'content': content,
        'created_at': datetime.now().isoformat()
    })
    return doc_id


def get_secrets_for_role(role):
    return secrets_table.search(Secret.recipient_role == role)


def get_all_secrets():
    return secrets_table.all()


def create_audit_log(user_id, user_name, action, details):
    doc_id = audit_logs_table.insert({
        'user_id': user_id,
        'user_name': user_name,
        'action': action,
        'details': details,
        'created_at': datetime.now().isoformat()
    })
    return doc_id


def get_all_audit_logs():
    return audit_logs_table.all()


def create_maintenance(title, description, scheduled_date, scheduled_by, status='Scheduled'):
    doc_id = maintenance_table.insert({
        'title': title,
        'description': description,
        'scheduled_date': scheduled_date,
        'scheduled_by': scheduled_by,
        'status': status,
        'created_at': datetime.now().isoformat()
    })
    return doc_id


def get_all_maintenance():
    return maintenance_table.all()


def update_maintenance(maintenance_id, data):
    maintenance_table.update(data, doc_ids=[int(maintenance_id)])


def store_user_keys(user_id, public_key, private_key):
    existing = keys_table.search(Key.user_id == user_id)
    if existing:
        keys_table.update({'public_key': public_key, 'private_key': private_key}, Key.user_id == user_id)
    else:
        keys_table.insert({
            'user_id': user_id,
            'public_key': public_key,
            'private_key': private_key
        })


def get_user_keys(user_id):
    docs = keys_table.search(Key.user_id == user_id)
    if docs:
        return docs[0]
    return None


def get_public_key_for_role(role):
    users = users_table.search(User.role == role)
    if users:
        user_id = str(users[0].doc_id)
        keys = get_user_keys(user_id)
        if keys:
            return keys.get('public_key')
    return None


def get_payment_by_invoice(invoice_id):
    docs = payments_table.search(Payment.invoice_id == invoice_id)
    if docs:
        return docs[0]
    return None
