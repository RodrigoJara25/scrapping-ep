"""
Monitor de novedades del listado de /api/normas.

Toma una "foto" del listado y la compara con la foto anterior de la MISMA
fecha de consulta. Sirve para comprobar empiricamente si durante el dia se
agregan normas y si esas normas nuevas son siempre extraordinarias.

Uso:
    python tools/monitor_novedades.py                 # usa la API en Render
    python tools/monitor_novedades.py --local         # usa el scraper directo (sin servidor)
    python tools/monitor_novedades.py --api http://127.0.0.1:8000
    python tools/monitor_novedades.py --fecha 2026-09-11

Cada foto se guarda en tools/snapshots/<fechaConsulta>__<AAAAMMDD-HHMMSS>.json
y se imprime el diff contra la foto previa de esa misma fecha.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import urllib.request
from datetime import datetime

API_DEFAULT = "https://bot-el-peruano.onrender.com"
SNAP_DIR = os.path.join(os.path.dirname(__file__), "snapshots")


def _via_api(base: str, fecha: str | None) -> dict:
    url = f"{base}/api/normas" + (f"?fecha={fecha}" if fecha else "")
    # Si la API exige clave, toma la misma variable API_KEY del entorno.
    headers = {"X-API-Key": os.environ["API_KEY"]} if os.environ.get("API_KEY") else {}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = json.load(r)
    return payload["data"] if "data" in payload else payload


def _via_local(fecha: str | None) -> dict:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from datetime import date

    from app import scraper  # noqa: PLC0415

    d = date.fromisoformat(fecha) if fecha else None
    raw = scraper.listar_normas(d)
    # normalizar a camelCase minimo que usa este script
    return {
        "fechaConsulta": raw["fecha_consulta"],
        "total": raw["total"],
        "totalExtraordinarias": raw["total_extraordinarias"],
        "normas": [
            {
                "id": n["id"],
                "tipo": n["tipo"],
                "entidad": n["entidad"],
                "resolucion": n["resolucion"],
                "esExtraordinaria": n["es_extraordinaria"],
            }
            for n in raw["normas"]
        ],
    }


def _tomar_foto(data: dict) -> dict:
    normas = [
        {
            "pos": i,
            "id": n["id"],
            "tipo": n.get("tipo", ""),
            "esExtraordinaria": bool(n["esExtraordinaria"]),
            "entidad": n.get("entidad", ""),
            "resolucion": n.get("resolucion", ""),
        }
        for i, n in enumerate(data["normas"])
    ]
    return {
        "capturadoEn": datetime.now().astimezone().isoformat(timespec="seconds"),
        "fechaConsulta": data["fechaConsulta"],
        "total": data["total"],
        "totalExtraordinarias": data["totalExtraordinarias"],
        "normas": normas,
    }


def _foto_previa(fecha_consulta: str) -> dict | None:
    patron = os.path.join(SNAP_DIR, f"{fecha_consulta}__*.json")
    previos = sorted(glob.glob(patron))
    if not previos:
        return None
    with open(previos[-1], encoding="utf-8") as f:
        return json.load(f)


def _guardar(foto: dict) -> str:
    os.makedirs(SNAP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    ruta = os.path.join(SNAP_DIR, f"{foto['fechaConsulta']}__{ts}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(foto, f, ensure_ascii=False, indent=1)
    return ruta


def _diff(previa: dict, actual: dict) -> None:
    ids_prev = {n["id"] for n in previa["normas"]}
    ids_act = {n["id"] for n in actual["normas"]}
    nuevas = [n for n in actual["normas"] if n["id"] not in ids_prev]
    quitadas = [n for n in previa["normas"] if n["id"] not in ids_act]

    print(f"  Foto previa : {previa['capturadoEn']}  "
          f"total={previa['total']}  extra={previa['totalExtraordinarias']}")
    print(f"  Foto actual : {actual['capturadoEn']}  "
          f"total={actual['total']}  extra={actual['totalExtraordinarias']}")
    print()

    if not nuevas and not quitadas:
        print("  SIN CAMBIOS: mismos id que la foto anterior.")
        return

    if nuevas:
        n_ext = sum(1 for n in nuevas if n["esExtraordinaria"])
        n_nor = len(nuevas) - n_ext
        max_pos = max(n["pos"] for n in nuevas)
        bloque_superior = max_pos < actual["totalExtraordinarias"]
        print(f"  NUEVAS: {len(nuevas)}  ({n_ext} extraordinarias, {n_nor} normales)")
        print(f"  ¿Todas las nuevas son extraordinarias?  {'SI' if n_nor == 0 else 'NO'}")
        print(f"  ¿Todas dentro del bloque superior?      {'SI' if bloque_superior else 'NO'}")
        for n in nuevas:
            marca = "EXTRA" if n["esExtraordinaria"] else "normal"
            print(f"    pos {n['pos']:>3}  [{marca}] {n['tipo']:2} {n['id']:12} "
                  f"{n['entidad'][:34]:34} {n['resolucion'][:40]}")

    if quitadas:
        print(f"\n  DESAPARECIDAS: {len(quitadas)}")
        for n in quitadas:
            print(f"    {n['id']:12} {n['entidad'][:34]:34} {n['resolucion'][:40]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=API_DEFAULT, help="URL base de la API")
    ap.add_argument("--local", action="store_true", help="usar el scraper directo (sin servidor)")
    ap.add_argument("--fecha", default=None, help="fecha YYYY-MM-DD (por defecto, la del dia)")
    args = ap.parse_args()

    data = _via_local(args.fecha) if args.local else _via_api(args.api, args.fecha)
    foto = _tomar_foto(data)

    previa = _foto_previa(foto["fechaConsulta"])
    ruta = _guardar(foto)

    print(f"Foto guardada: {ruta}")
    print(f"Fecha consultada: {foto['fechaConsulta']}  "
          f"total={foto['total']}  extraordinarias={foto['totalExtraordinarias']}")
    print("-" * 72)
    if previa is None:
        print("  Es la PRIMERA foto de esta fecha. Vuelve a correr mas tarde para comparar.")
    else:
        _diff(previa, foto)


if __name__ == "__main__":
    main()
