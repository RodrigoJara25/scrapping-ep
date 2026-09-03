"""
API local del bot de scraping del Diario Oficial El Peruano.

Expone DOS funcionalidades pensadas para ser usadas como *tools* por un agente:

  1. GET /api/normas
     Lista las normas legales del dia (o de una fecha / rango dado):
     entidad, titulo, resolucion, fecha de publicacion y sumilla de cada una.

  2. GET /api/normas/{norma_id}
     Descarga individual de una norma concreta:
       - ?formato=texto  (por defecto) -> JSON con el texto integro, para
         resumir o responder preguntas.
       - ?formato=pdf                  -> el PDF oficial (application/pdf).
     Atajo binario directo: GET /api/normas/{norma_id}/pdf

Ejecutar:  python run.py       (o)   uvicorn app.main:app --reload
Docs:      http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException, Path, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__, scraper
from .models import ContenidoNorma, ListadoNormas, Norma

app = FastAPI(
    title="Bot Normas Legales - El Peruano",
    description=__doc__,
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def _parse_fecha(valor: str | None, campo: str) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"'{campo}' debe tener formato YYYY-MM-DD (recibido: {valor!r}).",
        )


def _validar_tipo(tipo: str) -> str:
    tipo = (tipo or "NL").upper()
    if tipo not in scraper.TIPOS_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"'tipo' debe ser uno de {scraper.TIPOS_VALIDOS} (recibido: {tipo!r}).",
        )
    return tipo


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@app.get("/", tags=["meta"])
def raiz() -> dict:
    return {
        "servicio": "Bot Normas Legales - El Peruano",
        "version": __version__,
        "endpoints": {
            "listado_del_dia": "/api/normas",
            "listado_por_fecha": "/api/normas?fecha=2026-09-03",
            "listado_por_rango": "/api/normas?fecha=2026-09-01&fecha_fin=2026-09-03",
            "contenido_individual": "/api/normas/{norma_id}?tipo=NL&formato=texto",
            "pdf_individual": "/api/normas/{norma_id}/pdf?tipo=NL",
            "docs": "/docs",
        },
    }


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/api/normas",
    response_model=ListadoNormas,
    tags=["normas"],
    summary="Listar normas legales (del dia, de una fecha o de un rango)",
)
def listar_normas(
    fecha: str | None = Query(
        None,
        description="Fecha a consultar en formato YYYY-MM-DD. Si se omite, se "
        "devuelve la ultima edicion publicada (la del dia).",
        examples=["2026-09-03"],
    ),
    fecha_fin: str | None = Query(
        None,
        description="Opcional. Fin del rango (YYYY-MM-DD). Requiere 'fecha'.",
        examples=["2026-09-03"],
    ),
) -> ListadoNormas:
    d_ini = _parse_fecha(fecha, "fecha")
    d_fin = _parse_fecha(fecha_fin, "fecha_fin")
    if d_fin and not d_ini:
        raise HTTPException(status_code=422, detail="'fecha_fin' requiere tambien 'fecha'.")

    try:
        data = scraper.listar_normas(d_ini, d_fin)
    except scraper.ScraperError as e:
        raise HTTPException(status_code=502, detail=f"Error de scraping: {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Error consultando El Peruano: {e}")

    return ListadoNormas(
        fecha_consulta=data["fecha_consulta"],
        fecha_fin=data["fecha_fin"],
        total=data["total"],
        total_extraordinarias=data["total_extraordinarias"],
        generado_en=data["generado_en"],
        normas=[Norma(**n) for n in data["normas"]],
    )


@app.get(
    "/api/normas/{norma_id}",
    tags=["normas"],
    summary="Descarga individual de una norma (texto para resumir, o PDF)",
    responses={
        200: {
            "content": {
                "application/json": {},
                "application/pdf": {},
            },
            "description": "JSON con el texto (formato=texto) o el PDF (formato=pdf).",
        },
        404: {"description": "Norma no encontrada"},
    },
)
def descargar_norma(
    norma_id: str = Path(
        ...,
        description="Identificador del dispositivo, p. ej. '2550147-1'.",
        pattern=r"^\d+-\d+$",
        examples=["2550147-1"],
    ),
    tipo: str = Query("NL", description="'NL' (normas legales) o 'EX' (extraordinaria)."),
    formato: str = Query(
        "texto",
        description="'texto' -> JSON con el contenido integro; 'pdf' -> archivo PDF.",
        pattern="^(texto|pdf|json)$",
    ),
):
    tipo = _validar_tipo(tipo)

    try:
        if formato == "pdf":
            contenido, nombre = scraper.descargar_pdf(norma_id, tipo)
            return Response(
                content=contenido,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
            )

        data = scraper.obtener_contenido(norma_id, tipo)
        return JSONResponse(ContenidoNorma(**data).model_dump())

    except scraper.NormaNoEncontrada as e:
        raise HTTPException(status_code=404, detail=str(e))
    except scraper.ScraperError as e:
        raise HTTPException(status_code=502, detail=f"Error de scraping: {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Error consultando El Peruano: {e}")


@app.get(
    "/api/normas/{norma_id}/pdf",
    tags=["normas"],
    summary="Atajo: PDF oficial de la norma (binario)",
    response_class=Response,
)
def descargar_norma_pdf(
    norma_id: str = Path(..., pattern=r"^\d+-\d+$", examples=["2550147-1"]),
    tipo: str = Query("NL", description="'NL' o 'EX'."),
) -> Response:
    tipo = _validar_tipo(tipo)
    try:
        contenido, nombre = scraper.descargar_pdf(norma_id, tipo)
    except scraper.NormaNoEncontrada as e:
        raise HTTPException(status_code=404, detail=str(e))
    except scraper.ScraperError as e:
        raise HTTPException(status_code=502, detail=f"Error de scraping: {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Error consultando El Peruano: {e}")

    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
