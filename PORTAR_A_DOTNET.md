# Especificación para portar el scraper a .NET

El bot actual (Python/FastAPI) ya funciona y sirve de **referencia / oráculo**:
para validar el port, comparar que la salida .NET coincide con
`https://bot-el-peruano.onrender.com/api/normas?fecha=YYYY-MM-DD` para la misma
fecha.

La lógica de scraping vive en `app/scraper.py` (~250 líneas, comentado). Esto es
el resumen accionable.

---

## 1. Endpoints a exponer (mismos que la versión Python)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/normas?fecha=&fecha_fin=` | Listado del día (o fecha / rango `YYYY-MM-DD`) |
| GET | `/api/normas/{id}?tipo=NL&formato=texto\|pdf` | Individual: JSON con texto íntegro, o el PDF |
| GET | `/api/normas/{id}/pdf?tipo=NL` | Atajo: PDF binario |
| GET | `/health` | `{"status":"ok"}` |

`tipo` ∈ `{NL, EX}` (default `NL`).

---

## 2. Llamadas HTTP upstream

Todas requieren cabecera `User-Agent` de navegador, p. ej.:
`Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36`

### A) Listado del día
```
GET https://diariooficial.elperuano.pe/Normas/LoadNormasLegales?Length=0
Header: X-Requested-With: XMLHttpRequest
```
Devuelve un **fragmento HTML** con bloques `<article>`.

### B) Listado por fecha / rango
```
POST https://diariooficial.elperuano.pe/Normas/Filtro?dateparam={MM/DD/YYYY 00:00:00 URL-encoded}
Headers:
  X-Requested-With: XMLHttpRequest
  Content-Type: application/x-www-form-urlencoded
  Referer: https://diariooficial.elperuano.pe/Normas
Body: cddesde={DD/MM/YYYY}&cdhasta={DD/MM/YYYY}
```
Mismo formato de respuesta que A.
**Ojo:** `dateparam` va en `MM/DD/YYYY`; el body va en `DD/MM/YYYY`.

### C) Detalle (texto íntegro)
```
GET https://busquedas.elperuano.pe/dispositivo/{tipo}/{id}
```
- `tipo` incorrecto → HTTP 404 → reintentar con el otro (`NL` <-> `EX`).
- La respuesta es una página HTML; la parte útil es `<div class="story">`.

### D) PDF
1. Del HTML de C, extraer el token con regex:
   `archivo/(?:file|thumbnail)/([A-Za-z0-9_\-]{10,})/`
2. ```
   GET https://busquedas.elperuano.pe/api/archivo/file/{token}/*/{id}.PDF
   Header: Referer: https://busquedas.elperuano.pe/dispositivo/{tipo}/{id}/pdf
   ```
3. Respuesta: `application/pdf`, el cuerpo empieza con `%PDF`. Validar eso.

Este camino sirve para normas regulares **y** para las 'Publicacion Digital'
(probado 24/24). Si `_dig` alguna vez no tuviera token, usar el fallback E.

### E) PDF directo de 'Publicacion Digital' (fallback)
El Peruano publica estas con un enlace **directo al PDF** (no al visor):
```
GET https://epdoc2.elperuano.pe/EpPo/VistaDE.asp?Referencias={ref}
```
donde `ref = base64("<id><yyyymmdd>")`, p. ej. `id=2549494-1`, fecha `2026-09-03`
-> base64 de `"2549494-120260903"` -> `MjU0OTQ5NC0xMjAyNjA5MDM=`.
Devuelve `application/pdf; Charset=UTF-8`, cuerpo `%PDF`. Requiere la **fecha de
publicacion** (viene en el listado). El bot Python expone esto como
`?fecha=YYYY-MM-DD` en `/api/normas/{id}/pdf` y en el listado ya deja
`ruta_pdf` con `&fecha=...` y `url_pdf_oficial` apuntando a este enlace directo
para las digitales.

---

## 3. Parseo del fragmento de listado

Seleccionar **todos** los `<article>` cuya clase **contenga** `edicionesoficiales_articulos`
(esto abarca `edicionesoficiales_articulos` **y** `edicionesoficiales_articulos_dig`).
> Saltarse el `_dig` fue el bug de "83 en vez de 88". No lo omitas.

Por cada `<article>`:

| Campo | De dónde | Regla |
|-------|----------|-------|
| `entidad` | `.ediciones_texto h4` | texto; quitar sufijo "Publicación Digital" |
| `es_publicacion_digital` | idem | `true` si el h4 decía "Publicación Digital" **o** si el `href` del h5 no es `/dispositivo/...` |
| `resolucion` | `.ediciones_texto h5 a` | texto del enlace |
| `tipo` + `id` | `href` del h5 a | si matchea `/dispositivo/(NL\|EX)/(\d+-\d+)` → grupos 1 y 2 |
| `id` (digital) | si el href **no** matchea | 1) del `src` de `.ediciones_pdf img`: regex `/(\d+-\d+)_Portada` · 2) o del parámetro `Referencias=` (base64) → decodificar → tomar el `\d+-\d+` inicial. `tipo = "NL"` |
| `fecha_publicacion` | `.ediciones_texto p` que tiene `<b>` con "Fecha:" | regex `(\d{2}/\d{2}/\d{4})` → convertir a ISO `YYYY-MM-DD` |
| `es_extraordinaria` | `.ediciones_texto` | `true` si existe `strong.extraordinaria` |
| `sumilla` | el/los `<p>` de `.ediciones_texto` que **no** son el de "Fecha:" | unir con espacio |
| `numero` | de `resolucion` | regex `N[°º]\s*([A-Za-z0-9\-./]+)` |
| `url_portada` | `.ediciones_pdf img[src]` | tal cual |
| `url_detalle` | construido | `https://busquedas.elperuano.pe/dispositivo/{tipo}/{id}` |
| `url_pdf_oficial` | construido | `{url_detalle}/pdf` |

Decodificar entidades HTML (`&#211;` → `Ó`, etc.) — cualquier parser HTML serio lo hace. Salida en **UTF-8**.

Dedupe por `(tipo, id)`.

---

## 4. Parseo de la página de detalle (C)

Contenedor: `div.story` (o `#x{id}`).

| Campo | De dónde |
|-------|----------|
| `titulo` / `sumilla` | `h1.sumilla` |
| `resolucion` | `h2.resoluci-n` (puede haber 1..n) → unir con espacio |
| `texto_completo` | todos los `p.cuerpo` → unir con `\n\n`; descartar el `<p>` que es solo el `id` |
| `fecha_documento` (opcional) | regex sobre el texto: `(\d{1,2})\s+de\s+([a-zA-Zñ]+)\s+d[eo]l?\s+(\d{4})` → ISO |

---

## 5. Modelo de salida (JSON)

### `GET /api/normas`
```jsonc
{
  "fecha_consulta": "2026-09-08",
  "fecha_fin": null,
  "total": 88,
  "total_extraordinarias": 0,
  "generado_en": "2026-09-08T15:04:05Z",
  "normas": [
    {
      "id": "2550147-1", "tipo": "NL",
      "entidad": "CULTURA",
      "titulo": "Designan Director ...",
      "resolucion": "RESOLUCIÓN MINISTERIAL N° 000318-2026-MC",
      "numero": "000318-2026-MC",
      "fecha_publicacion": "2026-09-08",
      "fecha_publicacion_texto": "08/09/2026",
      "sumilla": "Designan Director ...",
      "es_extraordinaria": false,
      "es_publicacion_digital": false,
      "url_detalle": "https://busquedas.elperuano.pe/dispositivo/NL/2550147-1",
      "url_pdf_oficial": "https://busquedas.elperuano.pe/dispositivo/NL/2550147-1/pdf",
      "url_portada": "https://elperuano.pe/.../2550147-1_Portada.jpg",
      "ruta_contenido": "/api/normas/2550147-1?tipo=NL",
      "ruta_pdf": "/api/normas/2550147-1/pdf?tipo=NL"
    }
  ]
}
```

### `GET /api/normas/{id}?formato=texto`
```jsonc
{
  "id": "2550147-1", "tipo": "NL",
  "titulo": "...", "resolucion": "...", "numero": "...",
  "fecha_documento": "2026-09-01",
  "sumilla": "...",
  "texto_completo": "San Borja, 1 de septiembre del 2026\n\nVISTOS: ...",
  "n_caracteres": 2391,
  "url_detalle": "...", "url_pdf_oficial": "...",
  "ruta_pdf": "/api/normas/2550147-1/pdf?tipo=NL"
}
```

### `formato=pdf`
`Content-Type: application/pdf`, `Content-Disposition: attachment; filename="{id}.pdf"`, cuerpo = bytes.

Errores: `422` (fecha/tipo/id mal formados), `404` (no existe / sin PDF), `502` (El Peruano no respondió).

---

## 6. Stack .NET sugerido

- **ASP.NET Core Minimal API**
- **HttpClient** vía `IHttpClientFactory`; `DefaultRequestHeaders.UserAgent` fijo. Manejar redirects y `404`.
- **AngleSharp** (mejor soporte de selectores CSS) o **HtmlAgilityPack** para el parseo.
- PDF: `Results.File(bytes, "application/pdf", $"{id}.pdf")`.
- Respetar salida `Content-Type: application/json; charset=utf-8`.

## 7. Gotchas

- `dateparam` = `MM/DD/YYYY`; body `cddesde`/`cdhasta` = `DD/MM/YYYY`.
- `NL` vs `EX`: probar el dado, si 404 probar el otro.
- Las publicaciones digitales (`article ..._dig`) **cuentan**: su enlace va a
  `VistaDE.asp`, el `id` sale de la portada o del base64 `Referencias=`.
  Para su PDF: el camino normal (detalle + token) funciona; el enlace directo
  `VistaDE.asp?Referencias=base64("<id><yyyymmdd>")` es el fallback y necesita
  la fecha de publicacion.
- Entidades HTML + UTF-8.
- El HTML de El Peruano puede cambiar: mantener la versión Python como oráculo
  para diffear resultados.
