#!/usr/bin/env python3
"""
fetch_opat.py — Grupo Saesa CCT
Hace login en OPAT, obtiene la agenda completa y guarda docs/data.json
Corre en GitHub Actions cada 5 minutos.
"""

import os, sys, json, time, traceback
from datetime import datetime, timezone

import requests

# ── Config desde variables de entorno (GitHub Secrets) ────────
OPAT_USER = os.environ.get("OPAT_USER", "")
OPAT_PASS = os.environ.get("OPAT_PASS", "")
OPAT_URL  = os.environ.get("OPAT_URL",  "https://opat.cl/agendaopat")
OUTPUT    = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")

def ts():
    return int(time.time() * 1000)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def save_error(msg):
    """Guarda un data.json con estado de error para que el dashboard lo muestre."""
    out = {
        "ok":           False,
        "error":        msg,
        "ultima_actualizacion": datetime.now(timezone.utc).isoformat(),
        "agenda":       []
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log(f"✗ Error guardado en data.json: {msg}")

def main():
    if not OPAT_USER or not OPAT_PASS:
        save_error("Credenciales no configuradas en GitHub Secrets (OPAT_USER / OPAT_PASS)")
        sys.exit(1)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer":    OPAT_URL + "/",
    })

    # ── 1. Cargar página principal para obtener cookies iniciales ──
    log("Cargando página principal de OPAT...")
    try:
        session.get(OPAT_URL + "/", timeout=15)
    except Exception as e:
        save_error(f"No se pudo acceder a {OPAT_URL}: {e}")
        sys.exit(1)

    # ── 2. Login ───────────────────────────────────────────────────
    log(f"Haciendo login como '{OPAT_USER}'...")
    try:
        r = session.post(
            OPAT_URL + "/api.php",
            data={
                "accion":   "login",
                "usuario":  OPAT_USER,
                "password": OPAT_PASS,
                "t":        ts(),
            },
            timeout=15,
        )
        r.raise_for_status()
        resp = r.json()
        log(f"Respuesta login: {resp}")

        # Verificar sesión
        chk = session.get(OPAT_URL + f"/api.php?accion=checkSession&t={ts()}", timeout=10)
        chk_data = chk.json()
        if not chk_data.get("success"):
            save_error(f"Login fallido o sesión no válida: {chk_data}")
            sys.exit(1)

        usuario = chk_data.get("usuario", {})
        log(f"✓ Sesión válida — {usuario.get('nombre','?')} ({usuario.get('perfil','?')})")

    except Exception as e:
        save_error(f"Error en login: {e}\n{traceback.format_exc()}")
        sys.exit(1)

    # ── 3. Obtener agenda ──────────────────────────────────────────
    log("Obteniendo agenda completa...")
    try:
        r = session.get(
            OPAT_URL + f"/api.php?accion=obtenerAgenda&t={ts()}",
            timeout=30,
        )
        r.raise_for_status()

        # Verificar que es JSON y no HTML (sesión expirada devuelve HTML)
        content_type = r.headers.get("Content-Type", "")
        if "html" in content_type or r.text.strip().startswith("<"):
            save_error("La respuesta de obtenerAgenda es HTML — sesión no autenticada")
            sys.exit(1)

        agenda = r.json()
        if not isinstance(agenda, list):
            save_error(f"Formato inesperado en obtenerAgenda: {str(agenda)[:200]}")
            sys.exit(1)

        log(f"✓ {len(agenda)} registros obtenidos")

    except Exception as e:
        save_error(f"Error obteniendo agenda: {e}")
        sys.exit(1)

    # ── 4. Guardar data.json ───────────────────────────────────────
    output = {
        "ok":                    True,
        "ultima_actualizacion":  datetime.now(timezone.utc).isoformat(),
        "usuario":               chk_data.get("usuario", {}),
        "total":                 len(agenda),
        "agenda":                agenda,
    }

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log(f"✓ data.json guardado con {len(agenda)} registros")

if __name__ == "__main__":
    main()
