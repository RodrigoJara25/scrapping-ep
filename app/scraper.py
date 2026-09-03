"""
Nucleo de web scraping del Diario Oficial El Peruano (seccion Normas Legales).

La web https://diariooficial.elperuano.pe/Normas carga el listado por AJAX contra
dos endpoints internos:

  * GET  /Normas/LoadNormasLegales?Length=0          -> edicion del dia (la ultima)
  * POST /Normas/Filtro?dateparam=MM/DD/YYYY...       -> filtrado por rango de fechas
        body: cddesde=DD/MM/YYYY&cdhasta=DD/MM/YYYY

Ambos devuelven un fragmento HTML con bloques <article class="edicionesoficiales_articulos">.

El detalle y el PDF de cada norma viven en otro dominio (busquedas.elperuano.pe):

  * GET /dispositivo/{tipo}/{id}                      -> HTML con el texto integro
  * GET /api/archivo/file/{token}/*/{id}.PDF          -> PDF binario
        (el {token} se extrae del HTML del detalle)

Todo funciona con requests + una cabecera User-Agent de navegador; no hay
proteccion anti-bot que bloquee las peticiones server-side.
"""

from __future__ import annotations

import base64
import re
from datetime import date, datetime, timezone

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# Configuracion
# --------------------------------------------------------------------------- #

BASE_DIARIO = "https://diariooficial.elperuano.pe"
BASE_BUSQUEDAS = "https://busquedas.elperuano.pe"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TIMEOUT = 30
TIPOS_VALIDOS = ("NL", "EX")

MESES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre",
    12: "diciembre",
}


# --------------------------------------------------------------------------- #
# Excepciones
# --------------------------------------------------------------------------- #

class ScraperError(Exception):
    """Error generico de scraping."""


class NormaNoEncontrada(ScraperError):
    """No se encontro la norma solicitada (id/tipo invalido o sin PDF)."""


# --------------------------------------------------------------------------- #
# Sesion HTTP
# --------------------------------------------------------------------------- #

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "es-PE,es;q=0.9",
        }
    )
    return s


# --------------------------------------------------------------------------- #
# Helpers de parseo
# --------------------------------------------------------------------------- #

_RE_DISPOSITIVO = re.compile(r"/dispositivo/([A-Za-z]+)/([0-9]+-[0-9]+)")
_RE_TOKEN = re.compile(r"archivo/(?:file|thumbnail)/([A-Za-z0-9_\-]{10,})/")
_RE_NUMERO = re.compile(r"N[°ºͦº°]\s*([A-Za-z0-9\-./]+)")
_RE_WS = re.compile(r"\s+")
_RE_ID_PORTADA = re.compile(r"/([0-9]+-[0-9]+)_Portada", re.IGNORECASE)
_RE_ID_SIMPLE = re.compile(r"^([0-9]+-[0-9]+)")
_RE_PUB_DIGITAL = re.compile(r"public\w*\s+digital", re.IGNORECASE)


def _limpiar(texto: str) -> str:
    return _RE_WS.sub(" ", (texto or "").replace("\xa0", " ")).strip()


def _fecha_iso(fecha_txt: str) -> str:
    """'03/09/2026' -> '2026-09-03'. Devuelve '' si no parsea."""
    fecha_txt = (fecha_txt or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(fecha_txt, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _extraer_numero(resolucion: str) -> str:
    m = _RE_NUMERO.search(resolucion or "")
    return m.group(1).strip(" .-") if m else ""


def _id_publicacion_digital(art) -> str:
    """Saca el id de una norma de 'Publicacion Digital' (article ..._dig),
    cuyo enlace no apunta a /dispositivo/ sino a VistaDE.asp."""
    # 1) imagen de portada:  .../PortadaFull/2026/09/03/2549494-1_Portada.jpg
    img = art.select_one(".ediciones_pdf img")
    if img and img.get("src"):
        mm = _RE_ID_PORTADA.search(img["src"])
        if mm:
            return mm.group(1)
    # 2) parametro Referencias= en base64  ->  "<id><yyyymmdd>"
    for a in art.select("a[href*='Referencias=']"):
        mm = re.search(r"Referencias=([A-Za-z0-9+/=]+)", a.get("href", ""))
        if not mm:
            continue
        try:
            decoded = base64.b64decode(mm.group(1) + "===").decode("latin1")
        except Exception:  # noqa: BLE001
            continue
        mm2 = _RE_ID_SIMPLE.match(decoded)
        if mm2:
            return mm2.group(1)
    return ""


def _parse_articulo(art) -> dict | None:
    """Convierte un <article class="edicionesoficiales_articulos[_dig]"> en un dict."""
    texto_div = art.select_one(".ediciones_texto")
    if texto_div is None:
        return None

    enlace = texto_div.select_one("h5 a")
    href = enlace.get("href", "") if enlace else ""
    m = _RE_DISPOSITIVO.search(href)
    if m:
        tipo, norma_id = m.group(1).upper(), m.group(2)
        es_digital = False
    else:
        # Publicacion Digital: el id vive en la portada o en el base64 del enlace
        norma_id = _id_publicacion_digital(art)
        if not norma_id:
            return None
        tipo = "NL"
        es_digital = True

    entidad = _limpiar(texto_div.select_one("h4").get_text(" ")) if texto_div.select_one("h4") else ""
    if _RE_PUB_DIGITAL.search(entidad):
        es_digital = True
        entidad = _limpiar(_RE_PUB_DIGITAL.sub("", entidad))
    resolucion = _limpiar(enlace.get_text()) if enlace else ""

    es_extra = texto_div.select_one("strong.extraordinaria") is not None

    # Fecha: esta dentro de un <p><b>Fecha: DD/MM/YYYY</b>...</p>
    fecha_txt = ""
    sumilla_parts: list[str] = []
    for p in texto_div.find_all("p"):
        b = p.find("b")
        if b and "fecha" in b.get_text(strip=True).lower():
            fm = re.search(r"(\d{2}/\d{2}/\d{4})", b.get_text())
            if fm:
                fecha_txt = fm.group(1)
            continue
        txt = _limpiar(p.get_text())
        if txt:
            sumilla_parts.append(txt)
    sumilla = " ".join(sumilla_parts).strip()

    portada = ""
    img = art.select_one(".ediciones_pdf img")
    if img and img.get("src"):
        portada = img["src"]

    url_pdf_oficial = ""
    for a in art.select("a.buttonaction"):
        h = a.get("href", "")
        if "/dispositivo/" in h and h.rstrip("/").endswith("/pdf"):
            url_pdf_oficial = h
            break
    if not url_pdf_oficial:
        url_pdf_oficial = f"{BASE_BUSQUEDAS}/dispositivo/{tipo}/{norma_id}/pdf"

    return {
        "id": norma_id,
        "tipo": tipo,
        "entidad": entidad,
        "titulo": sumilla,          # en el listado, el titulo largo y la sumilla coinciden
        "resolucion": resolucion,
        "numero": _extraer_numero(resolucion),
        "fecha_publicacion": _fecha_iso(fecha_txt),
        "fecha_publicacion_texto": fecha_txt,
        "sumilla": sumilla,
        "es_extraordinaria": es_extra,
        "es_publicacion_digital": es_digital,
        "url_detalle": f"{BASE_BUSQUEDAS}/dispositivo/{tipo}/{norma_id}",
        "url_pdf_oficial": url_pdf_oficial,
        "url_portada": portada,
        "ruta_contenido": f"/api/normas/{norma_id}?tipo={tipo}",
        "ruta_pdf": f"/api/normas/{norma_id}/pdf?tipo={tipo}",
    }


def _parse_listado(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    vistos: set[tuple[str, str]] = set()
    for art in soup.select('article[class*="edicionesoficiales_articulos"]'):
        item = _parse_articulo(art)
        if item and (item["tipo"], item["id"]) not in vistos:
            vistos.add((item["tipo"], item["id"]))
            out.append(item)
    return out


# --------------------------------------------------------------------------- #
# API publica del scraper
# --------------------------------------------------------------------------- #

def listar_normas(
    fecha: date | None = None,
    fecha_fin: date | None = None,
) -> dict:
    """
    Devuelve las normas legales publicadas.

    * Sin argumentos  -> ultima edicion disponible (la del dia).
    * fecha            -> normas de ese dia.
    * fecha + fecha_fin-> normas en el rango [fecha, fecha_fin].
    """
    s = _session()

    if fecha is None:
        resp = s.get(
            f"{BASE_DIARIO}/Normas/LoadNormasLegales",
            params={"Length": 0},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=TIMEOUT,
        )
    else:
        fin = fecha_fin or fecha
        if fin < fecha:
            fecha, fin = fin, fecha
        resp = s.post(
            f"{BASE_DIARIO}/Normas/Filtro",
            params={"dateparam": fecha.strftime("%m/%d/%Y 00:00:00")},
            data={
                "cddesde": fecha.strftime("%d/%m/%Y"),
                "cdhasta": fin.strftime("%d/%m/%Y"),
            },
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{BASE_DIARIO}/Normas",
            },
            timeout=TIMEOUT,
        )

    resp.raise_for_status()
    normas = _parse_listado(resp.text)

    if fecha is None:
        fecha_consulta = normas[0]["fecha_publicacion"] if normas else date.today().isoformat()
        fecha_fin_iso = None
    else:
        fecha_consulta = fecha.isoformat()
        fecha_fin_iso = (fecha_fin or fecha).isoformat() if fecha_fin else None

    return {
        "fecha_consulta": fecha_consulta,
        "fecha_fin": fecha_fin_iso,
        "total": len(normas),
        "total_extraordinarias": sum(1 for n in normas if n["es_extraordinaria"]),
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "normas": normas,
    }


def _fetch_detalle(norma_id: str, tipo: str, s: requests.Session) -> tuple[str, str]:
    """Descarga el HTML del detalle probando NL/EX. Devuelve (html, tipo_real)."""
    tipo = (tipo or "NL").upper()
    orden = [tipo] + [t for t in TIPOS_VALIDOS if t != tipo]
    ultimo_error: Exception | None = None
    for t in orden:
        try:
            r = s.get(f"{BASE_BUSQUEDAS}/dispositivo/{t}/{norma_id}", timeout=TIMEOUT)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            if "story" in r.text or f'id="x{norma_id}"' in r.text or "resoluci" in r.text.lower():
                return r.text, t
        except requests.RequestException as e:  # noqa: PERF203
            ultimo_error = e
    if ultimo_error:
        raise NormaNoEncontrada(f"No se pudo obtener la norma {norma_id}: {ultimo_error}")
    raise NormaNoEncontrada(f"Norma {norma_id} no encontrada (tipos probados: {orden}).")


def obtener_contenido(norma_id: str, tipo: str = "NL") -> dict:
    """Devuelve metadatos + texto integro de una norma, listo para resumir."""
    s = _session()
    html, tipo_real = _fetch_detalle(norma_id, tipo, s)
    soup = BeautifulSoup(html, "lxml")

    story = soup.select_one("div.story") or soup.select_one(f"#x{norma_id}") or soup

    h1 = story.select_one("h1.sumilla") or story.select_one("h1")
    sumilla = _limpiar(h1.get_text()) if h1 else ""

    resol_parts = [
        _limpiar(h.get_text())
        for h in story.select("h2.resoluci-n, h2")
        if _limpiar(h.get_text())
    ]
    resolucion = " ".join(resol_parts)

    parrafos: list[str] = []
    for p in story.select("p.cuerpo, p"):
        txt = _limpiar(p.get_text())
        if not txt:
            continue
        if txt == norma_id or txt.replace(" ", "") == norma_id:
            continue
        parrafos.append(txt)
    texto_completo = "\n\n".join(parrafos).strip()

    # Fecha: primera fecha larga tipo "San Borja, 1 de septiembre del 2026"
    fecha_iso = ""
    fm = re.search(
        r"(\d{1,2})\s+de\s+([a-zA-Zñ]+)\s+d[eo]l?\s+(\d{4})", texto_completo, re.IGNORECASE
    )
    if fm:
        dia, mes_txt, anio = fm.groups()
        mes_num = next((k for k, v in MESES.items() if v == mes_txt.lower()), None)
        if mes_num:
            fecha_iso = f"{anio}-{mes_num:02d}-{int(dia):02d}"

    return {
        "id": norma_id,
        "tipo": tipo_real,
        "titulo": sumilla,
        "resolucion": resolucion,
        "numero": _extraer_numero(resolucion),
        "fecha_documento": fecha_iso,
        "sumilla": sumilla,
        "texto_completo": texto_completo,
        "n_caracteres": len(texto_completo),
        "url_detalle": f"{BASE_BUSQUEDAS}/dispositivo/{tipo_real}/{norma_id}",
        "url_pdf_oficial": f"{BASE_BUSQUEDAS}/dispositivo/{tipo_real}/{norma_id}/pdf",
        "ruta_pdf": f"/api/normas/{norma_id}/pdf?tipo={tipo_real}",
    }


def descargar_pdf(norma_id: str, tipo: str = "NL") -> tuple[bytes, str]:
    """Descarga el PDF oficial de la norma. Devuelve (contenido, nombre_archivo)."""
    s = _session()
    html, tipo_real = _fetch_detalle(norma_id, tipo, s)

    m = _RE_TOKEN.search(html)
    if not m:
        raise NormaNoEncontrada(
            f"No se encontro el token de archivo para la norma {norma_id}."
        )
    token = m.group(1)

    url = f"{BASE_BUSQUEDAS}/api/archivo/file/{token}/*/{norma_id}.PDF"
    r = s.get(
        url,
        headers={"Referer": f"{BASE_BUSQUEDAS}/dispositivo/{tipo_real}/{norma_id}/pdf"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()

    contenido = r.content
    if not contenido.startswith(b"%PDF"):
        raise ScraperError(
            f"La respuesta para {norma_id} no es un PDF valido "
            f"(content-type={r.headers.get('content-type')})."
        )
    return contenido, f"{norma_id}.pdf"
