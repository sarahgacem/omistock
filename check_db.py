
from backend import models, database
db = database.SessionLocal()
count = db.query(models.Product).count()
print(f"Product count: {count}")
db.close()
