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
| `services/themes.py` | Catálogo de temas visuales y validación de contraste |
| `services/ai_models.py` | Catálogo de variantes de modelo por proveedor |
| `services/pptx_privacy.py` | Saneado de metadatos del PPTX entregable |
| `services/auditoria.py` | Registro de auditoría y purga por retención |
| `SEGURIDAD.md` | Datos tratados, controles y riesgos aceptados |
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

**El raspado web está desactivado por defecto (`SCRAPER_ENABLED=0`).**
DuckDuckGo no está en la lista blanca de PythonAnywhere y responde 202/timeout
fuera de ella: el raspado fallaba *siempre*, pero gastaba ~33 s (3 intentos ×
10 s + backoff) antes de rendirse, y `/api/preview` y `/api/generate` lo
llamaban por separado. Una propuesta tardaba 78 s; ahora tarda 25. Si algún día
hay salida libre, se reactiva con `SCRAPER_ENABLED=1`; hay un cortacircuitos que
marca el host como caído tras el primer fallo del proceso.

**La complejidad y el sector se deducen del NOMBRE de la empresa.**
`analyze_company_intelligence` ya sabía leerlo, pero solo se llegaba a él por la
rama del raspado — que nunca corre — así que "Minera Las Bambas S.A." salía como
*Servicios Comerciales / Media*: alcance de empresa de servicios para una
minera. Ahora el nombre se clasifica siempre. Dos reglas que conviene respetar
al tocar las listas de palabras clave (`services/scraper.py`):

- Las claves deben ser **raíces que aparezcan en la razón social real**:
  `pesca` no está dentro de `pesquera`, ni `construccion` dentro de
  `constructora`. Ese fue justo el fallo.
- **Un sector industrial identificado implica complejidad Alta**, igual que en
  `_build_sector_info`. Sin esa regla las dos rutas se contradecían.

El sector que el consultor escribe a mano siempre manda sobre el deducido.

**El guardado de la configuración comercial es atómico.** Se valida todo antes
de escribir nada. Antes se validaba y escribía parámetro a parámetro dentro de
la transacción, y un `return ... 400` a mitad del bucle salía del `with conn:`
de forma normal, es decir **haciendo commit**: enviar `{tarifa: 999, igv: 0.99}`
dejaba la tarifa en 999 mientras el consultor leía "no válido".

**CORS está cerrado salvo que se declare `CORS_ORIGINS`.** `CORS(app)` a secas
abría la API a cualquier origen; con `API_TOKEN` vacío, cualquier web que el
consultor visitara podía leer `/api/proposals` y llevarse el historial de
clientes con sus montos. La UI se sirve desde el mismo Flask, así que no
necesita CORS.

**Nada que venga del usuario puede ser NaN ni infinito.** `float('nan')`
superaba `revenue <= 0` (toda comparación con NaN es False) y salía en la
respuesta como el literal `NaN`, que no es JSON válido: el navegador reventaba
ante un HTTP 200. `utils/validators.py:_numero_finito` es el único sitio por
donde deben pasar los números de entrada.

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

**En HTML, `step` es un desplazamiento desde `min`, no un redondeo.**
`min="1" step="1000"` hacía que el navegador solo aceptara 1, 1001, 2001…, así
que **toda cifra redonda era inválida** —incluido el valor por defecto del
campo— y el formulario no se podía enviar: la función principal de la
aplicación estaba rota desde la interfaz sin que ningún test de API lo notara.
Para importes usar `step="any"`. `tests/test_interfaz.py` comprueba que el
valor por defecto sea válido según sus propios atributos.

**La previsualización web y el PPTX tienen que contar lo mismo.**
`services/preview.py` y `services/ppt_generator.py` construyen el mismo deck por
caminos distintos y ya se desincronizaron: el preview llevaba "GROW with SAP"
fijo en el cierre, así que en una propuesta Private el consultor revisaba GROW y
el cliente recibía RISE. Ambos deben salir de `EDITION_LABELS`.

**El estado del chatbot no se deduce del texto de los mensajes.** El frontend
detectaba "falta la API key" buscando un trozo del mensaje de error; al
reescribir ese texto la detección dejó de casar en silencio. El servidor manda
`ia_disponible` (en la respuesta y en el primer render vía Jinja) y el
indicador sale de `fijarEstadoConectado()`, único sitio que puede poner
"Conectado".

**El tema visual se aplica intercambiando los globales de `ppt_generator`.**
Los colores y fuentes se leen como globales desde ~20 funciones (unas 100
referencias); pasarlos como parámetro obligaría a tocar todas esas firmas. En su
lugar `generate_deck` los intercambia, construye y restaura en un `finally`.
Dos consecuencias que hay que respetar:

- **Va bajo un cerrojo** (`_CERROJO_TEMA`). Con `--threads 4`, dos generaciones
  simultáneas con temas distintos se pisarían y saldría un deck con colores
  mezclados. Serializar cuesta espera; un PPTX mal coloreado delante de un
  cliente cuesta más.
- **Ningún argumento por defecto puede referenciar un color o fuente.** Python
  los evalúa al definir la función, así que `def _style_card(..., line_color=COLOR_CARD_LINE)`
  congelaba el azul de SEIDOR y se colaba en todos los demás temas. Para eso
  está el centinela `_DEL_TEMA`, que además convive con el `None` de
  `_style_card` (que significa "sin borde").

**Un tema sin contraste se rechaza, uno flojo solo avisa.** `services/themes.py`
calcula el ratio WCAG de los pares que el deck pinta de verdad. Por debajo de
4.5:1 en texto/fondo, blanco/cabecera o blanco/acento se devuelve 400: el deck
saldría con texto invisible, que es un fallo que este proyecto ya sufrió. El
gris corporativo (#919191 sobre #F6F6F6) se queda en 2.9:1, así que ese umbral
es **advertencia y no error**: un límite duro rechazaría la propia paleta de
SEIDOR y, peor, rechazaría un tema a medida por un color que el consultor ni
tocó.

**`normalizar_tema` es idempotente.** La ruta valida el tema y luego se lo pasa
al generador, que lo vuelve a normalizar. "Personalizado" se decide comparando
el resultado con el tema base, no por si el llamante mandó claves; si no, un
tema del catálogo sin tocar acababa etiquetado como personalizado.

**La variante de IA se resuelve por llamada, no en el constructor.** El cliente
del proveedor se crea una vez al arrancar con su clave, pero el modelo es solo
un parámetro de cada petición: así el consultor cambia de variante sin reiniciar
ni tocar el `.env`. `services/ai_models.py` valida contra el catálogo del
proveedor activo — y admite además el modelo que haya en la variable de entorno,
para no romper un despliegue que ya funcionaba. **El proveedor (Gemini o Groq)
no se puede cambiar en caliente**, solo la variante dentro de él.

**El PPTX se sanea antes de entregarse.** Un .pptx es un ZIP y arrastra mucho
más que las láminas: el deck salía con el nombre de dos empleados en
`author`/`last_modified_by`, los 74 títulos de la plantilla interna, el esquema
de content types de **SharePoint de SEIDOR** (14,7 KB en `customXml/`), una
miniatura del deck original y `created: 2022`. Todo eso llegaba al cliente.
`services/pptx_privacy.py` fija las propiedades antes de guardar y reescribe el
ZIP después para quitar las partes que python-pptx no sabe eliminar. Si el
saneado falla **se conserva el archivo original**: un deck con metadatos de más
es mejor que ninguno delante de un cliente. Al tocar el generador, comprobar con
`tests/test_seguridad.py::TestPrivacidadDelDeck` que el paquete sigue íntegro.

**`@rate_limit` va SIEMPRE encima de `@require_auth`.** Los decoradores se
aplican de abajo arriba, así que el de arriba corre primero. Con el orden
contrario los 401 no consumían cupo y el token se podía probar por fuerza bruta
sin límite (medido: 40 intentos, cero 429).

**Las excepciones HTTP del framework se re-lanzan.** El `except Exception` de
cada vista convertía el 413 de Werkzeug en un 500 con el mensaje equivocado.
Toda vista lleva `except HTTPException: raise` antes del genérico.

**Tras un proxy, `request.remote_addr` no es el cliente.** En PythonAnywhere
Flask veía `10.0.4.129` (el balanceador) para todos, así que el limitador metía
a todos los consultores en el mismo cupo. Se corrige con `TRUST_PROXY_COUNT`,
que debe declarar el número **exacto** de proxies: de más, permite falsificar
`X-Forwarded-For` y saltarse el límite.

**Toda acción sobre datos de cliente deja rastro.** `services/auditoria.py`
registra generación, descarga, borrado, cambios de tarifas y purgas. El endpoint
es de solo lectura a propósito. Al añadir una operación sobre `proposals`,
añadir también su `registrar(...)`.

**Las dependencias van fijadas con `==`.** Al fijarlas apareció que producción
usaba `python-dotenv 1.0.1`, con PYSEC-2026-2270. Antes de subir una versión:
`pip-audit -r requirements.txt` y la suite completa.

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
- **Probar siempre a 375 px antes de dar por buena una pantalla.** Dos fallos
  solo visibles ahí: el nav sin `flex-wrap` hacía scrollear la página entera en
  horizontal, y la barra de conversaciones quedaba aplastada a 1 px porque en
  un flex en columna `max-height` limita por arriba pero no pone suelo (hace
  falta `flex: 0 0 auto`).
- **Un `python app.py` anterior puede seguir ocupando el puerto 5000** aunque su
  terminal ya no exista: el servidor nuevo arranca, no puede enlazar y sigues
  viendo el código viejo. En Windows:
  `Get-NetTCPConnection -LocalPort 5000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }`.
