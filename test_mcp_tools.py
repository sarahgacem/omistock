import httpx
import json
from datetime import datetime

API_BASE_URL = "http://localhost:8000"

with open("token.txt", "r") as f:
    TOKEN = f.read().strip()

headers = {"Authorization": f"Bearer {TOKEN}"}

print("=" * 62)
print("   MCP Server OMISTOCK - Test des outils (Standalone)")
print("=" * 62)

# ---- get_stock_alerts ----
r1 = httpx.get(f"{API_BASE_URL}/api/alerts", headers=headers, timeout=10)
alertes = r1.json()
if not alertes:
    result1 = "Tout est en ordre. Aucun produit en alerte."
else:
    result1 = "ALERTE STOCK :\n" + "\n".join(
        f"  - {p['name']} : seulement {p.get('quantity', 0)} restants !" for p in alertes
    )

output1 = {
    "tool": "get_stock_alerts",
    "parameters": {},
    "status_http": r1.status_code,
    "result": result1
}
print()
print(json.dumps(output1, ensure_ascii=False, indent=2))

# ---- get_business_summary ----
r2 = httpx.get(f"{API_BASE_URL}/api/sales", headers=headers, timeout=10)
sales = r2.json()
today = datetime.now().date()
today_sales = []
for s in sales:
    try:
        d = datetime.fromisoformat(s["date"].replace("Z", "+00:00")).date()
        if d == today:
            today_sales.append(s)
    except:
        pass
use = today_sales if today_sales else sales
nb = len(use)
ca = sum(s.get("total_amount", 0) for s in use)
periode = "aujourd'hui" if today_sales else "au total"
result2 = f"Vous avez fait {nb} ventes {periode} pour un total de {ca} DA."

output2 = {
    "tool": "get_business_summary",
    "parameters": {},
    "status_http": r2.status_code,
    "result": result2
}
print()
print(json.dumps(output2, ensure_ascii=False, indent=2))

print()
print("=" * 62)
print("  Note : donnees brutes retournees par le serveur MCP.")
print("  L'analyse est generee par le LLM (Claude) en aval.")
print("=" * 62)
