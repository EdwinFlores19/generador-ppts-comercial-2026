# CLAUDE.md — Contexto del proyecto

Generador de propuestas comerciales SAP S/4HANA Cloud en PowerPoint para
**SEIDOR Consulting SAC (Perú)**. Flask + python-pptx + SQLite, con un chatbot
de IA para preventa.

## Arranque rápido

```bash
pip install -r requirements.txt
python app.py                 # http://127.0.0.1:5000
python -m pytest tests/ -q    # ~4 min (genera PPTX reales, no hay mocks)
```

La BBDD y las tablas se crean solas al arrancar (`models/database.py:init_db`).

## Cómo está organizado

| Ruta | Responsabilidad |
| :--- | :--- |
| `app.py` | Factory de Flask, registro de blueprints, `init_db()` |
| `routes/main.py` | Vistas HTML (`/`, `/chatbot`) |
| `routes/proposals.py` | API del formulario clásico: preview, generate, download, delete, config |
| `routes/chat.py` | API del chatbot: sesiones, mensajes, generación desde conversación |
| `services/ppt_generator.py` | Construye el PPTX sobre la plantilla corporativa |
| `services/financial_engine.py` | Lee el Excel del estimador y calcula costos, ROI y advertencias |
| `services/scope_items.py` | Catálogo de Scope Items SAP leído de la hoja `S0` del Excel |
| `services/ai_chat.py` | Motor de IA dual: Gemini o Groq según `AI_PROVIDER` |
| `services/scraper.py` | Perfilado del prospecto (con fallback sectorial) |
| `services/preview.py` | Estructura de láminas para la previsualización web |
| `utils/paging.py` | `parse_paging` / `paging_headers` — paginación de los listados |
| `static/common.js` | `escapeHtml`, `authHeaders`, `fetchJson`, `showToast`, `descargarArchivo` — **compartido** |
| `deploy/RUNBOOK.md` | Operación en producción. **Leer antes de tocar el despliegue.** |

## Decisiones que conviene conocer antes de cambiar algo

**El PPTX se construye sobre la plantilla real de SEIDOR.**
`Capacitación de Joule - El futuro de SAP.pptx` (49 MB) aporta los fondos de
ondas, el logo y el cierre con los contactos. El generador borra sus 63
diapositivas y añade las suyas reutilizando **layouts por nombre exacto**
(`services/ppt_generator.py:LAYOUT_SPEC_*`). No cambiar a búsqueda por palabra
clave: así se elegían layouts con foto donde el texto blanco quedaba invisible.

**Conteo de láminas: 11 en complejidad Media, 12 en Alta** (la extra es
"Alcance Funcional Parte II: CO & PS"). Si se añade o quita una lámina hay que
actualizar `tests/test_ppt.py`, `scripts/verify_components.py` y
`services/preview.py` a la vez — ya se desincronizaron una vez.

**Los Scope Items salen del Excel, no de código.** `services/scope_items.py`
parsea la columna `SAP S/4HANA BP` de la hoja `S0`. Si los consultores
actualizan el estimador, la lámina se actualiza sola. Hay un catálogo de
respaldo por si el Excel no está disponible.

**Los siete parámetros comerciales viven en la BBDD**, no en el código
(`configuracion_comercial`, editables desde el panel de Ajustes): tarifa,
AMS, margen SaaS, años de ROI, IGV, tipo de cambio y `factor_ahorro`.

**El motor financiero devuelve `summary['advertencias']`.** Son avisos internos
para el consultor (ROI negativo, payback fuera del horizonte). **No se imprimen
en el PPTX**: se muestran en la web antes de presentar al cliente.

**No sanear en exceso los nombres de empresa.** `utils/sanitize.py` preserva
apóstrofos y ampersands a propósito: el nombre se imprime tal cual en la
portada y razones sociales reales como `D'Onofrio S.A.` se estaban mutilando.
La seguridad la dan las consultas parametrizadas, el saneo del nombre de
archivo y el escapado de HTML/XML — no esta función.

**Los dos listados se paginan en servidor**, con el helper compartido
`utils/paging.py`: 50 elementos por defecto (`?limit=&offset=`, tope 200) y el
total en la cabecera `X-Total-Count`; el front acumula páginas con "Cargar más".
Se mantiene el array plano en el cuerpo a propósito: la API y los tests
dependen de esa forma. El orden lleva `id DESC` como segundo criterio porque
`created_at`/`updated_at` empatan entre filas del mismo segundo y la paginación
repetía registros.

**`GET /api/chat/sessions` es ligero**: devuelve título, fecha, `message_count`
y `tiene_datos`, **no** los mensajes. El detalle de una conversación se pide con
`GET /api/chat/sessions/<id>`, que sí los trae. Antes la barra lateral
descargaba el historial completo de todas las conversaciones en cada carga.

**Los tests corren contra una BBDD y un OUTPUT_DIR temporales.**
`tests/conftest.py` fija `DB_NAME` y `OUTPUT_DIR` a un directorio temporal
**antes** de importar la app (`models/database.py` y `services/financial_engine.py`
leen `DB_NAME` en tiempo de import). Antes cada corrida ensuciaba
`proposals.db` con cientos de filas y dejaba ~38 MB de PPTX por lámina en
`generated_decks/`. No hardcodear rutas de salida en los tests: leerlas de
`os.getenv("OUTPUT_DIR")`.

**Auth opcional, pero completa.** Si `API_TOKEN` está definido, **todas** las
rutas de datos exigen `Authorization: Bearer`; solo `/`, `/chatbot` y
`/api/health` quedan públicas. `tests/test_api.py::TestAuthCubreTodaLaSuperficie`
recorre la lista entera: al añadir una ruta nueva, añadirla ahí también.
`require_auth` es un no-op sin `API_TOKEN`, así que una ruta desprotegida no da
síntomas hasta producción — de ahí ese test.

`/download/<id>` también exige token, así que **no se puede enlazar con
`<a href>`**: una navegación del navegador no envía cabeceras. El front usa
`descargarArchivo()` de `common.js` (fetch + blob). El motivo de protegerla: los
ids son consecutivos y bastaba recorrer `/download/1..N` para bajarse las
propuestas de todos los clientes.

El frontend toma el token de `localStorage.seidor_api_token` vía `authHeaders()`
en `common.js`. Los scripts (`scripts/check_production.py`) lo leen de la
variable de entorno `API_TOKEN`.

## Convenciones

- Código, comentarios, commits y textos de UI **en español**.
- Los comentarios explican *por qué*, sobre todo cuando el código evita un bug
  concreto ya sufrido. Conservarlos al refactorizar.
- Sin mocks en los tests: se generan PPTX de verdad y se valida su estructura.
- `templates/*.html` llevan el JS embebido; lo compartido va en `common.js`.

## Trampas conocidas

- **Flask cachea las plantillas Jinja en producción**: un cambio en
  `templates/*.html` no se ve hasta que el proceso reinicia de verdad.
- **El botón "Reload" de PythonAnywhere no siempre funciona.** Método fiable:
  `touch /var/www/<dominio>_wsgi.py`. Ver `deploy/RUNBOOK.md`.
- **El plan gratuito apaga la web app cada ~1 mes**: es la causa #1 de caídas.
- **DuckDuckGo está bloqueado** por la lista blanca del plan gratuito; el
  scraper cae al fallback sectorial. Para clasificar bien, usar el chatbot.
- **El Excel del estimador se lee con copia en caliente** si Windows lo tiene
  bloqueado por estar abierto.
