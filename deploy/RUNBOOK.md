# Runbook de Operación — GROW Deck Automator

Guía operativa del despliegue en **PythonAnywhere** (plan gratuito).
URL de producción: `https://consultoredwinflores.pythonanywhere.com`

---

## 1. ⚠️ El sitio se apaga cada mes (causa #1 de caídas)

El plan gratuito de PythonAnywhere **deshabilita la web app cada ~1 mes** salvo
que alguien entre y confirme que sigue en uso. Cuando expira, el dominio
responde con la página *"Coming Soon: PythonAnywhere"* (HTTP 404) y **no** con
un error de la aplicación: el código está intacto, solo está apagada.

**Cómo reactivarla:**

1. Entrar a `pythonanywhere.com` e iniciar sesión.
2. Pestaña **Web**.
3. Pulsar el botón amarillo **"Run until 1 month from today"**.
4. Verificar: `curl https://consultoredwinflores.pythonanywhere.com/api/health`
   debe devolver `{"status": "healthy", ...}`.

**Prevención:** la fecha límite se muestra en la pestaña Web ("This site will be
disabled on ..."). PythonAnywhere envía un correo de aviso una semana antes a la
dirección de la cuenta. Conviene apuntarlo en el calendario como tarea mensual.

---

## 2. Desplegar una versión nueva

```bash
# En una consola Bash de PythonAnywhere
cd ~/generador-ppts-comercial-2026
git pull origin main
source ~/venv-seidor/bin/activate
pip install --no-cache-dir -r requirements.txt   # solo si cambió requirements.txt
```

Después hay que **reiniciar el proceso** para que tome los cambios.

### El botón "Reload" de la interfaz web no siempre funciona

Se ha observado que los clics en **Reload** desde la pestaña Web pueden no
registrarse (el proceso sigue sirviendo el código anterior). La comprobación
fiable es el log de errores: un reinicio real escribe una línea nueva
`[INFO] app: Aplicación GROW Deck inicializada correctamente.`

**Método alternativo, siempre funciona** — tocar el archivo WSGI desde la consola:

```bash
touch /var/www/consultoredwinflores_pythonanywhere_com_wsgi.py
```

Verificar que el reinicio ocurrió de verdad:

```bash
tail -5 /var/log/consultoredwinflores.pythonanywhere.com.error.log
```

**Ojo con las plantillas:** Flask en modo producción cachea las plantillas Jinja
compiladas en memoria. Un `git pull` que solo cambie `templates/*.html` **no se
refleja** hasta que el proceso reinicia de verdad.

---

## 3. Configurar el motor de IA del chatbot

El chatbot necesita una API key. Sin ella la aplicación funciona igual (el
generador por formulario no usa IA), pero el chat responde con un aviso.

Editar `~/generador-ppts-comercial-2026/.env` (pestaña **Files**):

```bash
# Opción A — Google Gemini
AI_PROVIDER=gemini
GEMINI_API_KEY=...          # https://aistudio.google.com/app/apikey

# Opción B — Groq (verificado: api.groq.com NO está bloqueado en el plan gratuito)
AI_PROVIDER=groq
GROQ_API_KEY=...            # https://console.groq.com/keys
GROQ_MODEL=llama-3.3-70b-versatile
```

Reiniciar después (sección 2). Comprobar el proveedor activo:

```bash
curl -s https://consultoredwinflores.pythonanywhere.com/chatbot | grep -o "Asistente IA · [^<]*"
```

Si el modelo por defecto de Groq quedara obsoleto, listar los vigentes:

```bash
curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
```

---

## 4. Límites del plan gratuito

| Recurso | Límite | Consumo del proyecto |
| :--- | :--- | :--- |
| Disco | 512 MB | ~210 MB (proyecto 93 MB + venv 116 MB) |
| CPU | 100 s/día | ~3-5 s por PPTX generado |
| Red saliente | Lista blanca de hosts | Gemini ✅ · Groq ✅ · DuckDuckGo ❌ |
| Web apps | 1 | 1 |
| Vigencia | ~1 mes (ver sección 1) | — |

El scraper de DuckDuckGo **está bloqueado** por la lista blanca: el sistema
detecta el fallo y aplica el *fallback* sectorial automáticamente (por eso las
propuestas del formulario suelen salir como "Servicios Comerciales / Media").
Para clasificación fiable conviene usar el **chatbot**, que infiere el sector con
IA, o forzar el sector y la complejidad en el formulario.

---

## 5. Diagnóstico rápido

| Síntoma | Causa probable | Acción |
| :--- | :--- | :--- |
| Página *"Coming Soon"* / 404 | La web app expiró | Sección 1 |
| Los cambios de código no se ven | El proceso no reinició | Sección 2 (`touch` del WSGI) |
| El chat responde "motor de IA no disponible" | Falta API key en `.env` | Sección 3 |
| Error 500 al generar | `Estimador S0 V2.0.xlsx` abierto/bloqueado | Cerrar el Excel; el sistema ya reintenta con copia temporal |
| Todo devuelve 401 | `API_TOKEN` definido en `.env` | En el navegador: `localStorage.setItem('seidor_api_token', '<token>')` |
| El PPT sale con ROI negativo | Facturación baja frente al alcance | La UI ya lo advierte: ajustar facturación, alcance o `factor_ahorro` en Ajustes |
| El botón Descargar no hace nada | Token ausente o caducado (`/download/<id>` también exige auth) | Mismo `localStorage.setItem(...)` de la fila anterior; la consola muestra el aviso |
| El historial solo muestra 50 filas | Es lo esperado: se pagina de 50 en 50 | Usar "Cargar más" al pie de la tabla |
| `scripts/check_production.py` devuelve 401 | El script no lleva token | `API_TOKEN=<token> python scripts/check_production.py` (acepta también `BASE_URL`) |

Logs:

```bash
tail -50 /var/log/consultoredwinflores.pythonanywhere.com.error.log    # errores y logs de la app
tail -50 /var/log/consultoredwinflores.pythonanywhere.com.access.log   # peticiones
```

---

## 6. Base de datos

SQLite en `~/generador-ppts-comercial-2026/proposals.db`, en el disco
**persistente** (sobrevive reinicios y despliegues). Se crea e migra sola al
arrancar (`models/database.py:init_db`), en modo WAL.

Respaldo antes de una migración de esquema:

```bash
cd ~/generador-ppts-comercial-2026
cp proposals.db "proposals.db.bak-$(date +%Y%m%d)"
```
