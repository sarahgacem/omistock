import os
import httpx
from mcp.server.fastmcp import FastMCP

# Création du serveur MCP
mcp = FastMCP("Omistock Intelligence")

# Configuration de l'URL du backend FastAPI (API REST)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("AGENT_API_KEY", "")


def get_headers() -> dict:
    return {"X-API-KEY": API_KEY}


@mcp.tool()
def get_stock_alerts() -> str:
    """
    Retourne la liste des produits en rupture ou sous le seuil d'alerte.
    Consomme l'API REST d'OMISTOCK via /api/alerts (authentification X-API-KEY).
    """
    try:
        response = httpx.get(
            f"{API_BASE_URL}/api/alerts",
            headers=get_headers(),
            timeout=10.0
        )
        response.raise_for_status()
        alertes = response.json()

        if not alertes:
            return "✅ Tout est en ordre. Aucun produit en alerte."

        reponse = "⚠️ ALERTE STOCK :\n"
        for p in alertes:
            reponse += f"- {p['name']} : seulement {p.get('quantity', 0)} restants !\n"
        return reponse

    except httpx.HTTPStatusError as e:
        return f"Erreur API ({e.response.status_code}) : {e.response.text}"
    except Exception as e:
        return f"Erreur lors de l'appel à l'API : {str(e)}"


@mcp.tool()
def get_business_summary() -> str:
    """
    Retourne un résumé business : ventes du jour et transferts de stock.
    Consomme les routes /api/sales et /api/logs de l'API REST d'OMISTOCK.
    """
    try:
        r_sales = httpx.get(
            f"{API_BASE_URL}/api/sales",
            headers=get_headers(),
            timeout=10.0
        )
        r_sales.raise_for_status()
        sales = r_sales.json()

        r_logs = httpx.get(
            f"{API_BASE_URL}/api/logs",
            headers=get_headers(),
            timeout=10.0
        )
        r_logs.raise_for_status()
        logs = r_logs.json()

        nb_ventes = len(sales)
        ca = sum(s.get("total_amount", 0) for s in sales)
        nb_transferts = sum(1 for l in logs if "Transfert" in l.get("action", ""))

        resume = f"Vous avez enregistré {nb_ventes} vente(s) pour un total de {ca} DA."
        if nb_transferts > 0:
            resume += f" Le système a également enregistré {nb_transferts} transfert(s) de stock."
        return resume

    except httpx.HTTPStatusError as e:
        return f"Erreur API ({e.response.status_code}) : {e.response.text}"
    except Exception as e:
        return f"Erreur lors de l'appel à l'API : {str(e)}"


@mcp.tool()
def predict_stockout(product_id: int) -> str:
    """
    Prédit le risque de rupture de stock pour un produit donné.
    Consomme /api/inventory et /api/sales de l'API REST d'OMISTOCK.
    """
    try:
        r_inv = httpx.get(
            f"{API_BASE_URL}/api/inventory",
            headers=get_headers(),
            timeout=10.0
        )
        r_inv.raise_for_status()
        inventory = r_inv.json()

        product = next((p for p in inventory if p.get("id") == product_id), None)
        if not product:
            return f"Produit {product_id} introuvable."

        quantity = product.get("quantity", 0)
        threshold = product.get("min_threshold", 5)
        name = product.get("name", f"Produit {product_id}")

        r_sales = httpx.get(
            f"{API_BASE_URL}/api/sales",
            headers=get_headers(),
            timeout=10.0
        )
        r_sales.raise_for_status()
        sales = r_sales.json()

        # Calcul de la consommation moyenne journalière
        product_sales = [
            item
            for s in sales
            for item in s.get("items", [])
            if item.get("product_id") == product_id
        ]
        total_sold = sum(i.get("quantity", 0) for i in product_sales)
        avg_daily = round(total_sold / 30, 2) if total_sold > 0 else 0

        if avg_daily > 0 and quantity > 0:
            days_left = round(quantity / avg_daily)
            if days_left <= 7:
                return (f"🔴 RISQUE ÉLEVÉ — {name} : {quantity} unités restantes, "
                        f"consommation ~{avg_daily}/jour → rupture dans ~{days_left} jour(s).")
            else:
                return (f"🟢 Stock correct — {name} : {quantity} unités restantes, "
                        f"consommation ~{avg_daily}/jour → rupture estimée dans ~{days_left} jour(s).")
        elif quantity <= threshold:
            return f"🟠 ATTENTION — {name} : {quantity} unités, sous le seuil d'alerte ({threshold})."
        else:
            return f"🟢 Stock correct — {name} : {quantity} unités (seuil : {threshold})."

    except httpx.HTTPStatusError as e:
        return f"Erreur API ({e.response.status_code}) : {e.response.text}"
    except Exception as e:
        return f"Erreur lors de l'appel à l'API : {str(e)}"


if __name__ == "__main__":
    mcp.run()
