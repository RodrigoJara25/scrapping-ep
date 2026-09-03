# Workflows de n8n

Orquestación del bot de El Peruano. n8n corre en Docker; el bot debe estar
accesible en `http://host.docker.internal:8000` (arráncalo con
`python run.py --host 0.0.0.0`).

## Credenciales necesarias en n8n

- **Google Sheets OAuth2 API**
- **Google Drive OAuth2 API**
- **OpenAI API** (para el agente)

Tras importar cada workflow hay que reasignar las credenciales en los nodos
Google/OpenAI y volver a seleccionar documento / hoja / carpeta en los
desplegables (n8n recarga así el esquema de columnas).

## IDs usados

| Recurso | ID |
|---|---|
| Sheet `Índice Normas` | `1ElUARBFkw4yDILsTYDX6UfrSp6RHoyTl5uGCf2phMRg` |
| Carpeta Drive `PDFs descargados` | `1xgCPsInswVhS4HhLl8xat6KkwAj4H5yL` |

El Sheet tiene 3 pestañas: `Normas` (la llena n8n), `Descargas` (la llena n8n),
`Vista` (fórmula QUERY de solo lectura: titulo · norma · fecha · sumilla).

---

## 1. `01_ingesta_diaria.json` — Ingesta diaria

`Schedule (09:00)` → `GET /api/normas` → `Split Out` → `Set` → `Google Sheets (appendOrUpdate por id)`

Guarda todas las normas del día en la pestaña `Normas`. `appendOrUpdate` con
`matchingColumns: id` evita duplicados si corre dos veces.

## 2. `02_descargar_y_archivar_norma.json` — Sub-workflow (tool del agente)

`Execute Workflow Trigger` (inputs: `id`, `tipo`, `resolucion`, `fecha_publicacion`)
→ descarga el PDF del bot → lo sube a Drive con nombre
`AAAA-MM-DD__SLUG-RESOLUCION__id.pdf` → lo hace accesible por enlace
→ registra fila en `Descargas` → marca `estado=descargado` en `Normas`
→ devuelve `{ ok, id, archivo, pdf_link }`.

> El nodo **Link publico** comparte el PDF con "cualquiera con el enlace".
> Bórralo si no quieres que sea público.

Prueba aislada — input fijo en el nodo `Inicio`:

```json
{ "id": "2550147-1", "tipo": "NL", "resolucion": "RESOLUCIÓN MINISTERIAL N° 000318-2026-MC", "fecha_publicacion": "2026-09-03" }
```

## 3. Agente `EP - Agente Normas Legales` (construir a mano)

Los nodos LangChain de n8n cambian mucho entre versiones, así que este no se
entrega como JSON. Nodos:

| # | Nodo | Configuración |
|---|------|---------------|
| 1 | **Chat Trigger** | sin cambios |
| 2 | **AI Agent** (Tools Agent) | System Message = `system_prompt.txt` |
| 3 | **OpenAI Chat Model** | credencial OpenAI, modelo `gpt-4o-mini` |
| 4 | **Simple Memory** (Window Buffer) | context window: 10 |
| 5 | **Tool HTTP Request** `listar_normas` | GET `http://host.docker.internal:8000/api/normas`, query `fecha` = *let the model define* |
| 6 | **Tool HTTP Request** `obtener_texto_norma` | GET `http://host.docker.internal:8000/api/normas/{id}`, query `tipo` = *model*, `formato` = `texto` |
| 7 | **Tool Call n8n Workflow** `descargar_y_archivar_norma` | apunta al workflow 2; inputs `id`, `tipo`, `resolucion`, `fecha_publicacion` (los define el modelo) |

Conecta 5, 6 y 7 al puerto *Tool* del agente.

El texto del System Message está en [`system_prompt.txt`](system_prompt.txt).
