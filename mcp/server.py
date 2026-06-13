import asyncio
from mcp.server.fastmcp import FastMCP
import sqlite3
import os

# Création du serveur MCP
mcp = FastMCP("Omistock Intelligence")

# Chemin vers la base de données (creee a la racine du projet par le backend)
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "stock.db"))

@mcp.tool()
def get_stock_alerts(company_id: int):
    """
    Analyse le stock et retourne la liste des produits en rupture ou presque.
    """
    if not os.path.exists(DB_PATH):
        return "Erreur : La base de données est introuvable."

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # On cherche les produits où la quantité est <= 5 (seuil arbitraire pour l'exemple)
    query = "SELECT name, quantity FROM products WHERE company_id = ? AND quantity <= 5"
    
    cursor.execute(query, (company_id,))
    alertes = cursor.fetchall()
    conn.close()
    
    if not alertes:
        return "✅ Tout est en ordre. Aucun produit en alerte."
    
    reponse = "⚠️ ALERTE STOCK :\n"
    for name, qty in alertes:
        reponse += f"- {name} : seulement {qty} restants !\n"
    
    return reponse

@mcp.tool()
def get_business_summary(company_id: int):
    """
    Lit les ventes et les logs d'activité pour fournir un résumé business textuel à l'IA.
    """
    if not os.path.exists(DB_PATH):
        return "Erreur : La base de données est introuvable."

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ventes d'aujourd'hui
    # En SQLite, 'now' est en UTC. Pour être large dans la démo, on prend les 24 dernières heures ou la journée.
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM sales WHERE company_id = ? AND date(date) = date('now')", (company_id,))
    today_sales = cursor.fetchone()
    
    # Ventes totales
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM sales WHERE company_id = ?", (company_id,))
    all_sales = cursor.fetchone()
    
    # Nombre de transferts récents (logs)
    cursor.execute("SELECT COUNT(*) FROM activity_logs WHERE company_id = ? AND action LIKE '%Transfert%'", (company_id,))
    nb_transferts = cursor.fetchone()[0]

    conn.close()
    
    if today_sales[0] > 0:
        nb_ventes = today_sales[0]
        ca = today_sales[1]
        periode = "aujourd'hui"
    else:
        nb_ventes = all_sales[0]
        ca = all_sales[1]
        periode = "au total"
        
    resume = f"Vous avez fait {nb_ventes} ventes {periode} pour un total de {ca} DA."
    
    if nb_transferts > 0:
        resume += f" Le système a également enregistré {nb_transferts} transfert(s) de stock."
        
    return resume

if __name__ == "__main__":
    mcp.run()
