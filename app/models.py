"""Modelos de datos (Pydantic) para la API del bot de El Peruano."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NormaItem(BaseModel):
    """Una norma legal en el listado. Nombres en camelCase por requerimiento del consumidor."""

    id: str
    tipo: str
    entidad: str = ""
    titulo: str = ""
    resolucion: str = ""
    numero: str = ""
    fechaPublicacion: str = ""
    fechaPublicacionTexto: str = ""
    sumilla: str = ""
    esExtraordinaria: bool = False
    esPublicacionDigital: bool = False
    urlDetalle: str = ""
    urlPdfOficial: str = ""
    urlCuadernillo: str = ""
    urlPortada: str = ""
    rutaContenido: str = ""
    rutaPdf: str = ""


class DataListado(BaseModel):
    """Cuerpo `data` de la respuesta del listado."""

    fechaConsulta: str
    fechaFin: str
    total: int
    totalExtraordinarias: int = 0
    generadoEn: str
    normas: list[NormaItem] = Field(default_factory=list)


class RespuestaListado(BaseModel):
    """Envoltura estandar de la respuesta del endpoint de listado."""

    statusCode: int = 200
    success: bool = True
    message: str | None = None
    data: DataListado


class ContenidoNorma(BaseModel):
    """Respuesta del endpoint individual cuando se pide el texto (formato=texto)."""

    id: str
    tipo: str
    titulo: str = ""
    resolucion: str = ""
    numero: str = ""
    fecha_documento: str = Field(
        "", description="Fecha que figura en el texto (emision/firma), ISO. Puede diferir de la de publicacion."
    )
    sumilla: str = ""
    texto_completo: str = Field("", description="Texto integro de la norma, listo para resumir")
    n_caracteres: int = 0
    url_detalle: str = ""
    url_pdf_oficial: str = ""
    ruta_pdf: str = Field("", description="Ruta local de esta API para descargar el PDF binario")


class ErrorRespuesta(BaseModel):
    detail: str
