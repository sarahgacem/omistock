import shutil
import datetime
import os

def backup_database():
    source = "stock.db"
    if not os.path.exists(source):
        print("Erreur : La base de données source 'stock.db' n'existe pas.")
        return

    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    destination = os.path.join(backup_dir, f"stock_backup_{timestamp}.db")

    try:
        shutil.copy2(source, destination)
        print(f"Succès : Sauvegarde créée -> {destination}")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde : {e}")

if __name__ == "__main__":
    backup_database()
