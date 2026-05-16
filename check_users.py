import os, sys
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import SessionLocal
from models import User

db = SessionLocal()
users = db.query(User).all()
for u in users:
    print(f"Email: {u.email}, Role: {u.user_type}, Branch: {u.branch_id}")
db.close()
