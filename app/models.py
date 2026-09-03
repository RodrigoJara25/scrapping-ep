"""Modelos de datos (Pydantic) para la API del bot de El Peruano."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Norma(BaseModel):
    """Una norma legal publicada en el Diario Oficial El Peruano."""

    id: str = Field(..., description="Identificador del dispositivo, p. ej. '2550147-1'")
    tipo: str = Field(
        ...,
        description="Tipo de publicacion: 'NL' (Normas Legales) o 'EX' (Edicion Extraordinaria)",
    )
    entidad: str = Field(
        "", description="Sector / entidad emisora, p. ej. 'CULTURA', 'EDUCACION'"
    )
    titulo: str = Field("", description="Titulo largo de la norma (sumilla del listado)")
    resolucion: str = Field(
        "", description="Denominacion de la resolucion, p. ej. 'RESOLUCION MINISTERIAL N 000318-2026-MC'"
    )
    numero: str = Field("", description="Numero de la resolucion si se pudo separar del texto")
    fecha_publicacion: str = Field(
        "", description="Fecha de publicacion en formato ISO (YYYY-MM-DD)"
    )
    fecha_publicacion_texto: str = Field(
        "", description="Fecha tal como aparece en la web (DD/MM/YYYY)"
    )
    sumilla: str = Field("", description="Pequeno resumen / extracto de la norma")
    es_extraordinaria: bool = Field(
        False, description="True si pertenece a una edicion extraordinaria"
    )
    es_publicacion_digital: bool = Field(
        False,
        description="True si es una 'Publicacion Digital' (municipalidades, etc.); "
        "el detalle y el PDF se obtienen igual con /api/normas/{id}",
    )
    url_detalle: str = Field("", description="URL publica con el detalle de la norma")
    url_pdf_oficial: str = Field(
        "", description="URL publica del visor de PDF en busquedas.elperuano.pe"
    )
    url_portada: str = Field("", description="URL de la imagen de portada del cuadernillo")
    # Rutas utiles para que un agente encadene la descarga individual
    ruta_contenido: str = Field(
        "", description="Ruta local de esta API para obtener el texto completo"
    )
    ruta_pdf: str = Field(
        "", description="Ruta local de esta API para descargar el PDF"
    )


class ListadoNormas(BaseModel):
    """Respuesta del endpoint de listado."""

    fecha_consulta: str = Field(..., description="Fecha (o rango) consultada, ISO")
    fecha_fin: str | None = Field(None, description="Fin del rango si se consulto un rango")
    total: int = Field(..., description="Cantidad de normas encontradas")
    total_extraordinarias: int = Field(
        0, description="Cantidad de normas de edicion extraordinaria"
    )
    generado_en: str = Field(..., description="Timestamp ISO de cuando se genero la respuesta")
    normas: list[Norma] = Field(default_factory=list)


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
