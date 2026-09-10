# Bot de scraping — Normas Legales de *El Peruano*

Extrae las **Normas Legales** que el Diario Oficial *El Peruano* publica cada día en
<https://diariooficial.elperuano.pe/Normas> y las expone mediante una **API local**
pensada para ser consumida por un agente como *tool*.

De cada norma se obtiene: **entidad/sector, título, resolución (y su número),
fecha de publicación y sumilla**. Además se puede descargar el **texto íntegro**
(para resumir / responder preguntas) y el **PDF oficial** (para enviárselo al usuario).

---

## Cómo funciona (sin navegador ni Selenium)

La web carga el listado por AJAX. El bot llama directamente a esos endpoints internos:

| Paso | Petición real que hace el bot |
|------|-------------------------------|
| Listado del día | `GET diariooficial.elperuano.pe/Normas/LoadNormasLegales?Length=0` |
| Listado por fecha/rango | `POST diariooficial.elperuano.pe/Normas/Filtro?dateparam=MM/DD/YYYY` con `cddesde`/`cdhasta` en `DD/MM/YYYY` |
| Texto íntegro de una norma | `GET busquedas.elperuano.pe/dispositivo/{tipo}/{id}` (HTML con `<div class="story">`) |
| PDF oficial | `GET busquedas.elperuano.pe/api/archivo/file/{token}/*/{id}.PDF` (el `token` se extrae del HTML anterior) |

Basta una cabecera `User-Agent` de navegador; no hay bloqueo anti-bot.

`tipo` es `NL` (Normas Legales) o `EX` (Edición Extraordinaria). Si se pasa el
tipo equivocado, el bot reintenta automáticamente con el otro.

---

## Instalación

```bash
cd ElPeruano
python -m venv .venv
.venv\Scripts\activate        # Windows   (source .venv/bin/activate en Linux/Mac)
pip install -r requirements.txt
```

## Ejecutar la API

```bash
python run.py                 # http://127.0.0.1:8000
python run.py --reload        # desarrollo con autorecarga
python run.py --port 9000
```

Documentación interactiva (Swagger): <http://127.0.0.1:8000/docs>

---

## API

### 1) `GET /api/normas` — listado

Lista las normas legales. Es la llamada que hace el agente **una vez al día**.

| Query param | Descripción |
|-------------|-------------|
| *(ninguno)* | Última edición publicada (la del día). |
| `fecha` | Día concreto en `YYYY-MM-DD`. |
| `fecha_fin` | Opcional. Fin de rango `YYYY-MM-DD` (requiere `fecha`). |

**Ejemplo**

```bash
curl "http://127.0.0.1:8000/api/normas"
curl "http://127.0.0.1:8000/api/normas?fecha=2026-09-03"
```

```jsonc
{
  "statusCode": 200,
  "success": true,
  "message": null,
  "data": {
    "fechaConsulta": "2026-09-03",
    "fechaFin": "2026-09-03",
    "total": 88,
    "totalExtraordinarias": 0,
    "generadoEn": "2026-09-03T15:04:05-05:00",
    "normas": [
      {
        "id": "2550147-1",
        "tipo": "NL",
        "entidad": "CULTURA",
        "titulo": "RESOLUCIÓN MINISTERIAL N° 000318-2026-MC",
        "resolucion": "RESOLUCIÓN MINISTERIAL N° 000318-2026-MC",
        "numero": "000318-2026-MC",
        "fechaPublicacion": "2026-09-03",
        "fechaPublicacionTexto": "03/09/2026",
        "sumilla": "Designan Director de Programa Sectorial II ...",
        "esExtraordinaria": false,
        "esPublicacionDigital": false,
        "urlDetalle": "https://busquedas.elperuano.pe/dispositivo/NL/2550147-1",
        "urlPdfOficial": "https://busquedas.elperuano.pe/dispositivo/NL/2550147-1/pdf",
        "urlCuadernillo": "https://busquedas.elperuano.pe/cuadernillo/NL/20260903",
        "urlPortada": "https://elperuano.pe/.../2550147-1_Portada.jpg",
        "rutaContenido": "/api/Agente/norma/2550147-1/contenido?tipo=NL",
        "rutaPdf": "/api/Agente/norma/2550147-1/pdf?tipo=NL"
      }
    ]
  }
}
```

Notas de esta respuesta:

- La respuesta va envuelta en `{ statusCode, success, message, data }`. Los errores
  (422 / 502) siguen devolviéndose como `{"detail": "..."}` con su HTTP status.
- `titulo` = `resolucion` (denominación de la norma). El texto descriptivo va en `sumilla`.
- `fechaFin` toma el valor de `fechaConsulta` cuando no se pasa un rango.
- `generadoEn` en hora de Perú (UTC-5).
- `rutaContenido` / `rutaPdf` apuntan a las rutas del servicio consumidor
  (`/api/Agente/norma/...`). En publicaciones digitales, `rutaPdf` incluye
  `&fecha=YYYY-MM-DD` (lo necesita la descarga del PDF de esas municipales).

### 2) `GET /api/normas/{norma_id}` — descarga individual

Se llama **cuando el usuario elige una norma** del listado.

| Query param | Descripción |
|-------------|-------------|
| `tipo` | `NL` (por defecto) o `EX`. |
| `formato` | `texto` (por defecto) → JSON con el texto íntegro. `pdf` → archivo PDF. |
| `fecha` | Solo para normas con `es_publicacion_digital: true`: la `fecha_publicacion` (YYYY-MM-DD) que trae el listado. Habilita el enlace directo de respaldo (`VistaDE.asp`). El listado ya la incluye en `ruta_pdf`. |

**Texto (para resumir / responder preguntas)**

```bash
curl "http://127.0.0.1:8000/api/normas/2550147-1?tipo=NL&formato=texto"
```

```jsonc
{
  "id": "2550147-1",
  "tipo": "NL",
  "titulo": "Designan Director de Programa Sectorial II ...",
  "resolucion": "RESOLUCIÓN MINISTERIAL N° 000318-2026-MC",
  "numero": "000318-2026-MC",
  "fecha_documento": "2026-09-01",
  "sumilla": "Designan Director de Programa Sectorial II ...",
  "texto_completo": "San Borja, 1 de septiembre del 2026\n\nVISTOS: ...",
  "n_caracteres": 2391,
  "url_detalle": "https://busquedas.elperuano.pe/dispositivo/NL/2550147-1",
  "url_pdf_oficial": "https://busquedas.elperuano.pe/dispositivo/NL/2550147-1/pdf",
  "ruta_pdf": "/api/normas/2550147-1/pdf?tipo=NL"
}
```

**PDF (para enviárselo al usuario)**

```bash
curl -L "http://127.0.0.1:8000/api/normas/2550147-1?tipo=NL&formato=pdf" -o norma.pdf
# atajo binario equivalente:
curl -L "http://127.0.0.1:8000/api/normas/2550147-1/pdf?tipo=NL"      -o norma.pdf
```

### Errores

| Código | Cuándo |
|--------|--------|
| `422` | `fecha` mal formada, `tipo` distinto de `NL`/`EX`, `id` que no es `\d+-\d+`. |
| `404` | La norma no existe (probados `NL` y `EX`) o no tiene PDF. |
| `502` | El Peruano no respondió o cambió su HTML. |

---

## Uso desde un agente

Flujo previsto:

1. **Una vez al día** → `GET /api/normas` → el agente muestra al usuario la lista
   (entidad, resolución, sumilla).
2. El usuario elige una → el agente toma su `id` y `tipo` de la lista.
3. `GET /api/normas/{id}?formato=texto` → el agente **resume** y **responde
   preguntas** sobre `texto_completo`.
4. `GET /api/normas/{id}/pdf` → el agente **envía el PDF** al usuario.

En [`examples/agent_tool.py`](examples/agent_tool.py) hay un cliente Python con las
tres funciones (`listar_normas`, `obtener_texto_norma`, `descargar_pdf_norma`) y
un esbozo de definición de *tools* en formato JSON-schema.

---

## Estructura

```
ElPeruano/
├── app/
│   ├── main.py       # FastAPI: los 2 endpoints
│   ├── scraper.py    # núcleo de scraping (requests + BeautifulSoup)
│   └── models.py     # modelos Pydantic de la respuesta
├── examples/
│   └── agent_tool.py # cómo llamar la API como tool desde un agente
├── n8n/              # workflows de n8n (ingesta diaria, descarga, agente)
├── deploy/
│   └── bot-elperuano.service   # unit systemd para VM Linux sin Docker
├── Dockerfile
├── docker-compose.yml
├── render.yaml       # despliegue en Render (alternativa pública)
├── run.py            # lanzador de uvicorn
└── requirements.txt
```

## Despliegue en una VM propia (sin hosting externo)

Si la organización no permite plataformas externas (Render, etc.) pero tiene
máquinas virtuales, el bot corre igual: es una app Python autónoma. Queda como
**API interna** en la red de la empresa; n8n la llama por la IP/hostname de la VM.

> Requisito: la VM necesita salida a internet hacia `diariooficial.elperuano.pe`
> y `busquedas.elperuano.pe`. Si hay proxy corporativo, define `HTTP_PROXY` /
> `HTTPS_PROXY` / `NO_PROXY` como variables de entorno (el bot las respeta sin
> cambios de código; ver plantillas en `docker-compose.yml` y `deploy/`).

### Opción 1 — Docker en la VM (recomendada)

```bash
git clone https://github.com/RodrigoJara25/scrapping-ep.git
cd scrapping-ep
docker compose up -d --build
docker compose logs -f bot-elperuano
```

- API en `http://<ip-de-la-vm>:8000`.
- Para otros contenedores de la misma red Docker: `http://bot-elperuano:8000`.
- `restart: unless-stopped` → arranca solo al reiniciar la VM.
- Actualizar: `git pull && docker compose up -d --build`.

**Si n8n ya corre en Docker en la misma VM:** descomenta el bloque `networks`
del `docker-compose.yml` (con el nombre real de la red de n8n) y en n8n usa
`http://bot-elperuano:8000`.

### Opción 2 — Linux sin Docker (systemd)

Ver instrucciones completas en [`deploy/bot-elperuano.service`](deploy/bot-elperuano.service).
Resumen: `git clone` en `/opt/bot-elperuano`, `venv` + `pip install`, copiar el
`.service`, `systemctl enable --now bot-elperuano`. El servicio se reinicia solo
y arranca en el boot.

### HTTPS interno

Normalmente HTTP dentro de la red interna basta. Si la política exige HTTPS,
pon un reverse proxy delante (nginx / Caddy) o usa el balanceador/ingress de la
empresa apuntando al puerto 8000.

---

## Despliegue como API pública con HTTPS (alternativa)

### Opción A — Render.com (recomendada, no depende de tu PC)

1. Sube el repo a GitHub.
2. En <https://render.com> → **New + → Blueprint** → conecta este repo (detecta `render.yaml`).
   O bien **New + → Web Service** manual:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health check path: `/health`
   - Plan: Free
3. Te queda una URL tipo `https://bot-el-peruano.onrender.com`.
   Prueba: `https://bot-el-peruano.onrender.com/api/normas`
4. En los workflows de n8n, cambia `http://host.docker.internal:8000` por esa URL.

> Plan free: la instancia "duerme" tras 15 min sin tráfico; la primera llamada
> tras dormir tarda ~50 s. Para una consulta al día es irrelevante.

### Opción B — ngrok (instantáneo, pero solo mientras tu PC esté encendida)

```bash
ngrok http 8000
```

Copia la URL `https://xxxx.ngrok-free.app` que te muestra. Requiere cuenta
gratuita y `ngrok config add-authtoken <token>` la primera vez. El bot debe
estar corriendo (`python run.py`).

### Nota de seguridad

La API no tiene autenticación: al publicarla, cualquiera con la URL puede
consultarla. Como solo expone información pública de El Peruano el riesgo es
bajo, pero si quieres cerrarla se puede añadir una cabecera `X-API-Key`.

## Notas

- El scraping depende del HTML de El Peruano; si cambian su web habrá que ajustar
  los selectores de `app/scraper.py`.
- Respeta un uso razonable del servicio (una consulta diaria + descargas puntuales).
- Solo lee información pública; no envía datos ni credenciales a El Peruano.
