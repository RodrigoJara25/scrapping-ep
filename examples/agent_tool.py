"""
Cliente de ejemplo: cómo un agente consume el bot de El Peruano como *tool*.

Arranca antes la API:  python run.py

Contiene:
  * 3 funciones cliente (listar / texto / pdf) que el agente invoca.
  * TOOLS: definición JSON-schema lista para registrar en un agente
    (Anthropic tools, OpenAI function calling, LangChain, etc.).
  * Un flujo de demostración en __main__.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

API_BASE = "http://127.0.0.1:8000"
TIMEOUT = 90


# --------------------------------------------------------------------------- #
# Funciones-tool
# --------------------------------------------------------------------------- #

def listar_normas(fecha: str | None = None, fecha_fin: str | None = None) -> dict:
    """Lista las normas legales del día (o de una fecha / rango 'YYYY-MM-DD')."""
    params = {}
    if fecha:
        params["fecha"] = fecha
    if fecha_fin:
        params["fecha_fin"] = fecha_fin
    r = requests.get(f"{API_BASE}/api/normas", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def obtener_texto_norma(norma_id: str, tipo: str = "NL") -> dict:
    """Devuelve metadatos + 'texto_completo' de una norma, para resumir o consultar."""
    r = requests.get(
        f"{API_BASE}/api/normas/{norma_id}",
        params={"tipo": tipo, "formato": "texto"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def descargar_pdf_norma(norma_id: str, tipo: str = "NL", destino: str | None = None) -> str:
    """Descarga el PDF oficial y devuelve la ruta local del archivo guardado."""
    r = requests.get(
        f"{API_BASE}/api/normas/{norma_id}/pdf",
        params={"tipo": tipo},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    ruta = Path(destino or f"{norma_id}.pdf")
    ruta.write_bytes(r.content)
    return str(ruta.resolve())


# --------------------------------------------------------------------------- #
# Definición de tools (JSON-schema) para registrar en el agente
# --------------------------------------------------------------------------- #

TOOLS = [
    {
        "name": "listar_normas_legales",
        "description": (
            "Lista las Normas Legales publicadas por el Diario Oficial El Peruano. "
            "Sin argumentos devuelve las del día. Úsala una vez al día para saber "
            "qué se publicó. Devuelve por cada norma: id, tipo (NL/EX), entidad, "
            "resolucion, numero, fecha_publicacion y sumilla."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Opcional. Día a consultar en formato YYYY-MM-DD.",
                },
                "fecha_fin": {
                    "type": "string",
                    "description": "Opcional. Fin de rango YYYY-MM-DD (requiere 'fecha').",
                },
            },
        },
    },
    {
        "name": "obtener_texto_norma",
        "description": (
            "Devuelve el texto íntegro de una norma legal concreta (campo "
            "'texto_completo') junto con sus metadatos. Úsala cuando el usuario "
            "elija una norma del listado para resumirla o responder preguntas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "norma_id": {"type": "string", "description": "id de la norma, p. ej. '2550147-1'."},
                "tipo": {"type": "string", "enum": ["NL", "EX"], "default": "NL"},
            },
            "required": ["norma_id"],
        },
    },
    {
        "name": "descargar_pdf_norma",
        "description": (
            "Descarga el PDF oficial de una norma legal y devuelve la ruta del "
            "archivo. Úsala cuando haya que enviarle el documento al usuario."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "norma_id": {"type": "string", "description": "id de la norma, p. ej. '2550147-1'."},
                "tipo": {"type": "string", "enum": ["NL", "EX"], "default": "NL"},
            },
            "required": ["norma_id"],
        },
    },
]

# Despacho nombre-de-tool -> función, para el bucle del agente.
DISPATCH = {
    "listar_normas_legales": listar_normas,
    "obtener_texto_norma": obtener_texto_norma,
    "descargar_pdf_norma": descargar_pdf_norma,
}


# --------------------------------------------------------------------------- #
# Demostración del flujo completo
# --------------------------------------------------------------------------- #

def _demo() -> None:
    print("1) Consultando normas del día...")
    data = listar_normas()
    print(f"   {data['total']} normas para {data['fecha_consulta']} "
          f"({data['total_extraordinarias']} extraordinarias)\n")

    for i, n in enumerate(data["normas"][:10], 1):
        print(f"   [{i}] {n['entidad']} — {n['resolucion']}")
        print(f"       {n['sumilla'][:110]}")

    if not data["normas"]:
        return

    elegida = data["normas"][0]
    print(f"\n2) El usuario elige la norma {elegida['id']} ({elegida['tipo']})")

    texto = obtener_texto_norma(elegida["id"], elegida["tipo"])
    print(f"   texto_completo: {texto['n_caracteres']} caracteres")
    print(f"   (primeras líneas) {texto['texto_completo'][:200]!r}\n")

    print("3) Descargando el PDF para enviárselo al usuario...")
    ruta = descargar_pdf_norma(elegida["id"], elegida["tipo"])
    print(f"   PDF guardado en: {ruta}")


if __name__ == "__main__":
    try:
        _demo()
    except requests.ConnectionError:
        sys.exit("No hay conexión con la API. Arráncala con:  python run.py")
