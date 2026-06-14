from werkzeug.security import generate_password_hash
from database import (
    users_table,
    create_user,
    get_user_by_username
)

def ensure_user(username, email, password, role, full_name):
    user = get_user_by_username(username)

    if user:
        
        users_table.update(
            {"password_hash": generate_password_hash(password)},
            doc_ids=[int(user.id)]
        )
        print(f"{role} password reset for {username}")

    else:
        
        create_user(
            username=username,
            email=email,
            password=password,
            role=role,
            full_name=full_name,
            phone="9999999999",
            address="System",
            approved=True
        )
        print(f"{role} created: {username}")


# ADMIN
ensure_user(
    username="admin@gmail.com",
    email="admin@gmail.com",
    password="admin@123",
    role="administrator",
    full_name="System Admin"
)

# DB MANAGER
ensure_user(
    username="dbmanager@gsmail.com",
    email="dbmanager@gsmail.com",
    password="dbManager@123",
    role="dbmanager",
    full_name="Database Manager"
)

print("Setup completed successfully")
