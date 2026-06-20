/**
 * OMISTOCK — Client API frontend partagé (refactor).
 *
 * Objectif : éliminer la duplication du code fetch/token/gestion d'erreur qui
 * était copié-collé dans chaque page HTML. Toutes les pages humaines doivent
 * passer par window.OmiAPI au lieu de réécrire fetch + headers + 401.
 *
 * Caractéristiques :
 * - Base URL = origine courante (le backend sert aussi le front).
 * - Jeton JWT humain stocké dans localStorage('omistock_token').
 * - Ajout automatique de l'en-tête Authorization: Bearer <token>.
 * - Redirection vers la page de login sur 401 (session expirée / absente).
 * - Helpers REST : get / post / put / del, et raccourcis métier (inventory,
 *   alerts, sales, restock, cycleCount, proposals, auditVerify).
 *
 * NB : c'est l'interface HUMAINE. Les agents IA n'utilisent JAMAIS ce client ;
 * ils passent par le serveur MCP -> /api/agent/* avec une X-API-Key scoped.
 */
(function () {
  "use strict";

  const API_BASE = window.location.origin;
  const TOKEN_KEY = "omistock_token";
  const LOGIN_PAGE = "index.html";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function authHeaders(extra) {
    const token = getToken();
    const headers = Object.assign(
      { "Content-Type": "application/json" },
      extra || {}
    );
    if (token) headers["Authorization"] = "Bearer " + token;
    return headers;
  }

  function requireAuthOrRedirect() {
    if (!getToken()) {
      window.location.href = LOGIN_PAGE;
      return false;
    }
    return true;
  }

  async function request(method, path, body, opts) {
    opts = opts || {};
    const url = path.startsWith("http") ? path : API_BASE + path;
    const init = {
      method: method,
      headers: authHeaders(opts.headers),
    };
    if (body !== undefined && body !== null) {
      init.body = typeof body === "string" ? body : JSON.stringify(body);
    }
    const res = await fetch(url, init);

    if (res.status === 401) {
      // Session expirée/invalide : on nettoie et on renvoie au login.
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem("omistock_user");
      window.location.href = LOGIN_PAGE;
      throw new Error("401 Unauthorized");
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        detail = j.detail || JSON.stringify(j);
      } catch (e) { /* corps non-JSON */ }
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    return ct.includes("application/json") ? res.json() : res.text();
  }

  const OmiAPI = {
    API_BASE: API_BASE,
    getToken: getToken,
    requireAuthOrRedirect: requireAuthOrRedirect,

    get: (p, o) => request("GET", p, null, o),
    post: (p, b, o) => request("POST", p, b, o),
    put: (p, b, o) => request("PUT", p, b, o),
    del: (p, o) => request("DELETE", p, null, o),

    // --- Raccourcis métier (alignés sur l'API refactorée) ---
    me: () => request("GET", "/api/me"),
    branches: () => request("GET", "/api/branches"),
    inventory: () => request("GET", "/api/inventory"),
    alerts: () => request("GET", "/api/alerts"),
    sales: () => request("GET", "/api/sales"),
    restock: (payload) => request("POST", "/api/restock", payload),

    // Inventaire physique / cycle count (théorie de gestion de stock).
    cycleCount: (payload) =>
      request("POST", "/api/inventory/cycle-count", payload),

    // File des propositions d'agents (human-in-the-loop).
    proposals: (status) =>
      request(
        "GET",
        "/api/agent/proposals" + (status ? "?status=" + encodeURIComponent(status) : "")
      ),
    approveProposal: (id) =>
      request("POST", "/api/agent/proposals/" + id + "/approve"),
    rejectProposal: (id) =>
      request("POST", "/api/agent/proposals/" + id + "/reject"),

    // Intégrité de l'audit (chaîne de hachage tamper-evident).
    auditVerify: () => request("GET", "/api/audit/verify"),
    logout: () => {
      localStorage.clear();
      window.location.href = LOGIN_PAGE;
    },
  };

  window.OmiAPI = OmiAPI;
})();
