#!/usr/bin/env python3
"""
MCP Server OMISTOCK - Test des 9 outils (Standalone)
Appelle directement l'API backend /api/agent/* pour valider chaque outil MCP.
"""
import json
import sys

import httpx

API = "http://localhost:8000"
API_KEY = ""

# Auto-detect API key from database
try:
    import os, sqlite3
    db_paths = [
        os.path.join(os.path.dirname(__file__), "stock.db"),
        os.path.join(os.path.dirname(__file__), "backend", "stock.db"),
    ]
    for db_path in db_paths:
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT api_key FROM users WHERE user_type='AGENT' AND api_key IS NOT NULL LIMIT 1"
            ).fetchone()
            if row:
                API_KEY = row[0]
            conn.close()
            break
except Exception:
    pass

if not API_KEY:
    print("ERREUR : Aucune cle API agent trouvee dans la base.")
    print("Lancez le backend et verifiez qu'un agent est configure.")
    sys.exit(1)

HEADERS = {"X-API-Key": API_KEY}
SEP = "=" * 64


def call(method, path, **kwargs):
    try:
        r = getattr(httpx, method)(f"{API}{path}", headers=HEADERS, timeout=10.0, **kwargs)
        return r.status_code, r.json()
    except httpx.ConnectError:
        return 0, {"error": "Backend non joignable (lancez uvicorn)"}
    except Exception as e:
        return 0, {"error": str(e)}


def show(tool_name, params, status, data):
    print()
    print(json.dumps({
        "tool": tool_name,
        "parameters": params,
        "status_http": status,
        "result": data if not isinstance(data, list) or len(data) <= 3
                  else data[:3] + [f"... ({len(data)} elements au total)"],
    }, indent=2, ensure_ascii=False, default=str))


print(SEP)
print("    MCP Server OMISTOCK - Test des outils (Standalone)")
print(SEP)

# 1. get_stock_alerts
s, d = call("get", "/api/agent/alerts")
if s == 200:
    if not d:
        result = "Tout est en ordre. Aucun produit en alerte."
    else:
        result = [{"name": p["name"], "on_hand": p["on_hand"], "rop": p["reorder_point"]} for p in d]
else:
    result = d
show("get_stock_alerts", {}, s, result)

# 2. get_inventory
s, d = call("get", "/api/agent/inventory")
show("get_inventory", {}, s, d)

# 3. get_stock_valuation
s, d = call("get", "/api/agent/valuation")
show("get_stock_valuation", {}, s, d)

# 4. predict_stockout (product_id=1)
s, d = call("get", "/api/agent/forecast/1")
show("predict_stockout", {"product_id": 1}, s, d)

# 5. get_reorder_suggestions
s, d = call("get", "/api/agent/reorder-suggestions")
show("get_reorder_suggestions", {}, s, d)

# 6. get_expiring_lots
s, d = call("get", "/api/agent/expiring-lots", params={"days": 30})
show("get_expiring_lots", {"days": 30}, s, d)

# 7. propose_restock
s, d = call("post", "/api/agent/proposals/restock", json={
    "product_id": 1, "branch_id": 1, "quantity": 10,
    "unit_cost": 150.0, "rationale": "Stock sous le ROP - test MCP"
})
show("propose_restock", {"product_id": 1, "branch_id": 1, "quantity": 10}, s, d)

# 8. list_my_proposals
s, d = call("get", "/api/agent/proposals/mine")
show("list_my_proposals", {}, s, d)

# 9. get_my_capabilities
s, d = call("get", "/api/agent/capabilities")
show("get_my_capabilities", {}, s, d)

print()
print(SEP)
print("  Note : donnees brutes retournees par le serveur MCP.")
print("  L'analyse est generee par le LLM (Claude) en aval.")
print(SEP)
