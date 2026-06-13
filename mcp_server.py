import os
import httpx
from mcp.server.fastmcp import FastMCP
from datetime import datetime

# Création du serveur MCP
mcp = FastMCP("Omistock Intelligence")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
# The API key should be provided via environment variables when running the MCP
API_KEY = os.getenv("AGENT_API_KEY", "")

def get_headers():
    headers = {}
    if API_KEY:
        headers["X-API-KEY"] = API_KEY
    return headers

@mcp.tool()
def get_stock_alerts() -> str:
    """
    Retourne la liste des produits en rupture de stock ou sous le seuil minimum.
    Note : cet outil fournit des données brutes. L'analyse et les recommandations
    sont générées par le LLM (Claude) qui consomme ces données.
    """
    try:
        response = httpx.get(f"{API_BASE_URL}/api/alerts", headers=get_headers(), timeout=10.0)
        response.raise_for_status()
        alertes = response.json()
        
        if not alertes:
            return "✅ Tout est en ordre. Aucun produit en alerte."
        
        reponse = "⚠️ ALERTE STOCK :\n"
        for prod in alertes:
            reponse += f"- {prod['name']} : seulement {prod.get('quantity', 0)} restants !\n"
        
        return reponse
    except httpx.HTTPStatusError as e:
        return f"Erreur de l'API ({e.response.status_code}) : L'action a été refusée ou le produit est introuvable."
    except Exception as e:
        return f"Erreur de communication avec l'API : {str(e)}"

@mcp.tool()
def get_business_summary() -> str:
    """
    Lit les ventes et les logs d'activité pour fournir un résumé business textuel à l'IA.
    """
    try:
        headers = get_headers()
        
        # 1. Récupérer les ventes
        sales_response = httpx.get(f"{API_BASE_URL}/api/sales", headers=headers, timeout=10.0)
        sales_response.raise_for_status()
        sales = sales_response.json()
        
        # 2. Récupérer les logs
        logs_response = httpx.get(f"{API_BASE_URL}/api/audit_logs", headers=headers, timeout=10.0)
        logs_response.raise_for_status()
        logs = logs_response.json()
        
        today = datetime.now().date()
        
        # Filter today's sales
        today_sales = []
        for s in sales:
            try:
                sale_date = datetime.fromisoformat(s['date'].replace('Z', '+00:00')).date()
                if sale_date == today:
                    today_sales.append(s)
            except:
                pass
        
        all_sales = sales
        
        # 3. Compter les transferts dans les logs
        nb_transferts = sum(1 for log in logs if 'Transfert' in log.get('action', ''))
        
        if len(today_sales) > 0:
            nb_ventes = len(today_sales)
            ca = sum(s.get('total_amount', 0) for s in today_sales)
            periode = "aujourd'hui"
        else:
            nb_ventes = len(all_sales)
            ca = sum(s.get('total_amount', 0) for s in all_sales)
            periode = "au total"
            
        resume = f"Vous avez fait {nb_ventes} ventes {periode} pour un total de {ca} DA."
        
        if nb_transferts > 0:
            resume += f" Le système a également enregistré {nb_transferts} transfert(s) de stock."
            
        return resume
    except httpx.HTTPStatusError as e:
        return f"Erreur de l'API ({e.response.status_code}) : L'action a été refusée ou non autorisée."
    except Exception as e:
        return f"Erreur de communication avec l'API : {str(e)}"

@mcp.tool()
def predict_stockout(product_id: int) -> str:
    """
    Outil d'intelligence artificielle : Analyse l'historique des logs (AuditLog)
    pour comparer la vitesse des ventes avec le stock restant et prédire une rupture.
    """
    try:
        payload = {"product_id": product_id}
        response = httpx.post(f"{API_BASE_URL}/api/mcp/analyze", json=payload, headers=get_headers(), timeout=10.0)
        response.raise_for_status()
        data = response.json()
        return data.get("analysis", "Analyse terminée, mais aucune conclusion retournée.")
    except httpx.HTTPStatusError as e:
        return f"Erreur de l'API ({e.response.status_code}) : {e.response.json().get('detail', 'Action refusée.')}"
    except Exception as e:
        return f"Erreur de communication avec l'API : {str(e)}"

if __name__ == "__main__":
    mcp.run()

