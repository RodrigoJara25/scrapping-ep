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

## 4b. Los 2 endpoints "difíciles" explicados paso a paso

**Ambos se apoyan en la MISMA petición**: la página de detalle
`GET https://busquedas.elperuano.pe/dispositivo/{tipo}/{id}`.
Es una SPA de React, pero pedida con un cliente HTTP normal (sin navegador, sin
JS) devuelve un HTML que **ya trae**: (a) el texto legal completo en marcado
antiguo, y (b) el token para bajar el PDF. Un solo GET sirve para los dos.

### Endpoint TEXTO — `GET /api/normas/{id}?formato=texto`

El HTML incluye este bloque (marcado simple, sin JS):
```html
<div class="story">
  <h1 class="sumilla">Ordenanza que aprueba la desafectación de uso de suelo </h1>
  <h1 class="sumilla">en el distrito de Puente Piedra</h1>
  <h2 class="resoluci-n ...">ORDENANZA N° 2847</h2>
  <p class="cuerpo ...">EL ALCALDE DE LA MUNICIPALIDAD METROPOLITANA DE LIMA</p>
  <p class="cuerpo ...">POR CUANTO:</p>
  <p class="cuerpo ...">El Concejo Metropolitano de Lima, en sesión ...</p>
  ...
  <p class="cuerpo"><span class="bold-cuerpo">2549494-1</span></p>   <!-- el id: se descarta -->
</div>
```
Pasos:
1. Resolver `tipo`: `GET .../dispositivo/{tipo}/{id}`; si 404 → probar el otro
   (`NL` <-> `EX`). El que dé 200 con `story` / `id="x{id}"` / `resoluci` en el
   body es el correcto. Header: solo `User-Agent` de navegador.
2. Dentro de `div.story` (fallback: `#x{id}`, o el documento entero):
   - `h1.sumilla` (¡pueden ser varios!) → unir textos con espacio → `titulo`/`sumilla`.
   - `h2.resoluci-n` (1..n) → unir con espacio → `resolucion`.
   - `p.cuerpo` en orden; **saltar** el `<p>` cuyo texto sea exactamente el `id`;
     unir el resto con `"\n\n"` → `texto_completo`.
3. Derivados: `numero` (regex sobre `resolucion`), `fecha_documento` (regex sobre
   el texto, best-effort), `n_caracteres` = largo de `texto_completo`.

### Endpoint PDF — `GET /api/normas/{id}/pdf`

El PDF **no está en URL predecible**. Se sirve por:
```
https://busquedas.elperuano.pe/api/archivo/file/{TOKEN}/*/{id}.PDF
```
`{TOKEN}` es una cadena opaca **por documento** (ej. `1QI_zBVxa_KA5zerdoc6Mw`),
incrustada en el HTML de detalle dentro de un blob de datos del React:
```
..."urlPDF","/api/archivo/file/1QI_zBVxa_KA5zerdoc6Mw/*/2549494-1.pdf","urlPDFTupa"...
```
Pasos:
1. Mismo `GET .../dispositivo/{tipo}/{id}` (resolver NL/EX).
2. Regex sobre el HTML crudo (texto, no DOM):
   `archivo/(?:file|thumbnail)/([A-Za-z0-9_\-]{10,})/` → grupo 1 = `{TOKEN}`.
3. `GET https://busquedas.elperuano.pe/api/archivo/file/{TOKEN}/*/{id}.PDF`
   con header `Referer: https://busquedas.elperuano.pe/dispositivo/{tipo}/{id}/pdf`.
   El `*` es **literal** (segmento de "versión" que su API acepta como comodín).
4. Validar: `Content-Type: application/pdf` y que los bytes empiecen con `%PDF`.
5. Devolver con `Content-Disposition: attachment; filename="{id}.pdf"`.

Fallback digital: si el token falla y hay `fecha` (ver sección E), armar
`base64("<id><yyyymmdd>")` y `GET .../EpPo/VistaDE.asp?Referencias={ref}`.

**Gotchas:**
- El `{TOKEN}` **cambia** si El Peruano reprocesa el documento → nunca cachearlo
  ni hardcodearlo; siempre re-scrapear de la página de detalle.
- `/dispositivo/{tipo}/{id}/pdf` en navegador = página del visor React, **no** el
  binario. No la bajes esperando bytes de PDF.

### Ejemplo real (norma `2549494-1`, tipo `NL`)
```
# 1) detalle — sirve para TEXTO y PDF
GET https://busquedas.elperuano.pe/dispositivo/NL/2549494-1
    -> div.story: resolucion="ORDENANZA N° 2847", texto_completo ~2175 chars
    -> regex token = 1QI_zBVxa_KA5zerdoc6Mw

# 2) PDF
GET https://busquedas.elperuano.pe/api/archivo/file/1QI_zBVxa_KA5zerdoc6Mw/*/2549494-1.PDF
    -> ~412 KB, empieza con %PDF-1.7

# 2b) fallback (misma norma)
GET https://epdoc2.elperuano.pe/EpPo/VistaDE.asp?Referencias=MjU0OTQ5NC0xMjAyNjA5MDM=
    -> el mismo PDF
```

---

## 5. Modelo de salida (JSON)

### `GET /api/normas`  (respuesta EXACTA que exige producción)

Envuelta en `{ statusCode, success, message, data }`. Nombres en camelCase,
respetando mayúsculas/minúsculas. Errores (422/502) NO se envuelven: siguen como
`{"detail": "..."}` con su HTTP status.

```jsonc
{
  "statusCode": 200,
  "success": true,
  "message": null,
  "data": {
    "fechaConsulta": "2026-09-10",
    "fechaFin": "2026-09-10",
    "total": 1,
    "totalExtraordinarias": 0,
    "generadoEn": "2026-09-10T14:40:20-05:00",
    "normas": [
      {
        "id": "2552687-1",
        "tipo": "NL",
        "entidad": "AMBIENTE",
        "titulo": "RESOLUCIÓN N° 038-2026-SENAMHI/JF",
        "resolucion": "RESOLUCIÓN N° 038-2026-SENAMHI/JF",
        "numero": "038-2026-SENAMHI/JF",
        "fechaPublicacion": "2026-09-10",
        "fechaPublicacionTexto": "10/09/2026",
        "sumilla": "Descripción de la norma",
        "esExtraordinaria": false,
        "esPublicacionDigital": false,
        "urlDetalle": "https://busquedas.elperuano.pe/dispositivo/NL/2552687-1",
        "urlPdfOficial": "https://busquedas.elperuano.pe/dispositivo/NL/2552687-1/pdf",
        "urlCuadernillo": "https://busquedas.elperuano.pe/cuadernillo/NL/20260910",
        "urlPortada": "https://elperuano.pe/NormasElperuano/PortadaFull/2026/09/10/2552687-1_Portada.jpg",
        "rutaContenido": "/api/Agente/norma/2552687-1/contenido?tipo=NL",
        "rutaPdf": "/api/Agente/norma/2552687-1/pdf?tipo=NL"
      }
    ]
  }
}
```

Reglas de esta respuesta:
- `titulo` = `resolucion` (denominación). El texto descriptivo va en `sumilla`.
- `fechaFin` = `fechaConsulta` cuando no hay rango explícito (nunca null).
- `generadoEn` en hora de Perú (UTC-5), precisión de segundos.
- `urlCuadernillo` = `https://busquedas.elperuano.pe/cuadernillo/{tipo}/{yyyymmdd}`
  (se toma del botón "Todo el cuadernillo" del listado; si no está, se construye).
- `rutaContenido` / `rutaPdf` apuntan al servicio consumidor (`/api/Agente/norma/...`).
  En publicaciones digitales, `rutaPdf` lleva además `&fecha=YYYY-MM-DD`.

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

## 5b. Origen de cada campo (IMPORTANTE para el port)

No todos los campos son de El Peruano. Al portar, respetar esta clasificacion.

### Tal cual del HTML de El Peruano
`entidad` (h4, sin el sufijo "Publicación Digital") · `resolucion` (texto del
h5>a) · `sumilla` (el `<p>` descriptivo) · `fecha_publicacion_texto`
("DD/MM/YYYY" literal) · `url_portada` (img src) · `id` (se **extrae** del href /
portada, pero el identificador es de ellos) · `titulo` del detalle (h1.sumilla) ·
`texto_completo` (p.cuerpo unidos).

### De la pagina pero transformado por el bot
- `fecha_publicacion`: su `DD/MM/YYYY` -> ISO `YYYY-MM-DD`.
- `numero`: regex `N[°º]\s*([A-Za-z0-9\-./]+)` sobre `resolucion`.
- `fecha_documento`: regex heuristico sobre el texto del cuerpo. **Puede venir
  vacio o impreciso** — no es un dato estructurado de El Peruano.
- `tipo`: `NL`/`EX` sale del href en las regulares; en las **digitales se asume
  `"NL"`** (funciona en la practica, pero es decision del bot).

### Calculado por el bot (no es un campo de El Peruano)
`es_extraordinaria` (hay `strong.extraordinaria`) · `es_publicacion_digital`
(article clase `_dig`) · `total` · `total_extraordinarias` · `n_caracteres`.

### Inventado por el bot (metadata de esta API — ignorar al scrapear)
- `fecha_consulta`, `fecha_fin`, `generado_en`: metadata de la respuesta.
- `titulo` en el **listado**: copia de `sumilla` (El Peruano solo da un texto ahi).
- `url_detalle`, `url_pdf_oficial`: URLs **construidas**. En regulares coinciden
  con enlaces de la pagina; en digitales las arma el bot (`VistaDE.asp`).
- `ruta_contenido`, `ruta_pdf`: rutas hacia ESTA API, sin sentido fuera de ella.
  El port .NET debe regenerarlas con sus propias rutas.

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
