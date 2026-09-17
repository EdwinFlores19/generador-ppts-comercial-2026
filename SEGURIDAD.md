# Seguridad y tratamiento de datos

Documento de referencia del generador de propuestas comerciales de **SEIDOR
Consulting SAC (Perú)**. Describe qué datos maneja el sistema, cómo se
protegen y qué queda pendiente. Está pensado para responder una revisión de
seguridad corporativa sin tener que leer el código.

Última revisión: auditoría de seguridad y cumplimiento de septiembre de 2026.

---

## 1. Qué datos trata el sistema

| Dato | Origen | Dónde vive | Sensibilidad |
| :--- | :--- | :--- | :--- |
| Razón social del prospecto | Lo escribe el consultor | `proposals`, PPTX | Comercial |
| Facturación anual estimada | Lo escribe el consultor | `proposals` | **Comercial sensible** |
| Tarifas, márgenes y tipo de cambio | `configuracion_comercial` | BBDD | **Interno de SEIDOR** |
| Importe y ROI de cada propuesta | Calculado | `proposals`, PPTX | **Comercial sensible** |
| Conversaciones del chatbot | El consultor y el modelo de IA | `chat_sessions` | Comercial |
| Registro de auditoría | Automático | `auditoria` | Interno |

**No se tratan datos personales de clientes**: el sistema trabaja con empresas
(razón social, facturación), no con personas físicas. La única excepción eran
los nombres de empleados que la plantilla filtraba en los metadatos del PPTX,
corregido (ver §3).

---

## 2. Controles implementados

### Autenticación y control de acceso
- Token Bearer opcional (`API_TOKEN`). Si está definido, **todas** las rutas de
  datos lo exigen; solo `/`, `/chatbot` y `/api/health` quedan públicas.
- Comparación en **tiempo constante** (`hmac.compare_digest`).
- Esquema `Bearer` validado estrictamente.
- Los intentos fallidos **consumen cupo del limitador** y quedan registrados en
  el log con ruta y origen.

### Límites y disponibilidad
- Límite de peticiones por IP y ventana (`RATE_LIMIT_MAX` / `RATE_LIMIT_WINDOW`).
- `TRUST_PROXY_COUNT` declara cuántos proxies hay delante para que el límite se
  aplique a la IP real. **Debe ser exacto**: declarar de más permite falsificar
  `X-Forwarded-For`.
- `MAX_CONTENT_LENGTH` (2 MB por defecto) contra agotamiento de memoria.
- Tiempo máximo de espera al proveedor de IA (`AI_TIMEOUT`, 25 s).

### Cabeceras y navegador
`Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options`,
`Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, y
`Strict-Transport-Security` sobre HTTPS. `Cache-Control: no-store` en las rutas
de datos y descargas.

CORS cerrado salvo que se declare `CORS_ORIGINS`.

### Entrada y salida
- Consultas SQL siempre parametrizadas.
- Escapado de HTML en el frontend (`escapeHtml`) antes de cualquier `innerHTML`;
  el markdown del chat se aplica **después** de escapar.
- Autoescape de Jinja activo, sin `|safe` en ninguna plantilla.
- Parser XML endurecido contra XXE en la generación del PPTX.
- Números de entrada validados y con rechazo de `NaN`/infinitos.
- Rutas de descarga y borrado contenidas dentro de `OUTPUT_DIR`.
- Los errores 500 no devuelven detalle interno; el detalle va al log.

### Confidencialidad del entregable
El `.pptx` se sanea antes de entregarse (ver §3).

### Trazabilidad
Tabla `auditoria` con acción, recurso, detalle, origen, resultado y fecha UTC.
Se registran: generación, descarga, borrado de propuestas, cambios de tarifas y
ejecuciones de purga. Consultable en `GET /api/auditoria`, **sin métodos de
escritura ni borrado**: un registro que la aplicación puede alterar no sirve
como evidencia.

### Conservación
`POST /api/retencion` aplica el plazo de `DIAS_RETENCION` (365 por defecto).
**Simula por defecto**; hay que enviar `{"confirmar": true}` para borrar.

### Cadena de suministro
Dependencias **fijadas con `==`**, auditadas con `pip-audit -r requirements.txt`
sin vulnerabilidades conocidas.

---

## 3. Hallazgos de la auditoría de septiembre de 2026

Todos corregidos y con test de regresión.

| # | Hallazgo | Severidad |
| :-- | :--- | :--- |
| 1 | **El PPTX entregado al cliente filtraba datos internos**: nombres de dos empleados (`author`, `last_modified_by`), los 74 títulos de lámina de la plantilla interna, el esquema de content types de **SharePoint de SEIDOR** (14,7 KB), una miniatura del deck interno original, y fechas que delataban una plantilla reciclada de 2022 | **Alta** |
| 2 | **Sin ninguna cabecera de seguridad** en producción: clickjacking y MIME sniffing posibles | **Alta** |
| 3 | **El límite de peticiones no distinguía usuarios**: tras el balanceador, Flask veía `10.0.4.129` para todos, así que una sola persona podía dejar sin servicio al resto | **Alta** |
| 4 | **Token expuesto a fuerza bruta sin límite**: 40 intentos fallidos, ninguna respuesta 429 | **Alta** |
| 5 | Comparación del token no constante (filtración por tiempo) y esquema `Bearer` no validado | Media |
| 6 | Sin límite de tamaño de petición: 12 MB aceptados y leídos en memoria | Media |
| 7 | Respuestas 500 devolviendo `str(e)` con rutas del servidor y mensajes de SQLite | Media |
| 8 | **Sin registro de auditoría**: no se sabía quién generó, descargó o borró qué | Media |
| 9 | **Sin plazo de conservación**: datos comerciales acumulados indefinidamente | Media |
| 10 | Dependencias sin fijar; al fijarlas apareció `python-dotenv 1.0.1` con PYSEC-2026-2270 | Media |
| 11 | Nombres de prospectos registrados a nivel INFO (minimización de datos) | Baja |
| 12 | Imagen Docker con compilador (`build-essential`) en la capa final | Baja |
| 13 | Contenedor sin `no-new-privileges` ni `cap_drop` | Baja |
| 14 | Errores del framework (413) convertidos en 500 por el `except` genérico | Baja |

---

## 4. Riesgos aceptados y limitaciones conocidas

Conviene declararlos: no todo es corregible dentro del alcance y el plan actual.

- **`'unsafe-inline'` en la CSP.** El JavaScript vive dentro de las plantillas
  HTML (decisión de diseño documentada en `CLAUDE.md`). La CSP sigue aportando:
  bloquea la carga de scripts de dominios ajenos, que es el vector real.
  Eliminarlo exige extraer todo el JS a ficheros y aplicar *nonces*.
- **Token único compartido.** No hay usuarios individuales, así que el registro
  de auditoría anota el origen de la petición, no una persona. El campo `actor`
  queda previsto para cuando haya login.
- **Sin cifrado en reposo.** La BBDD es un SQLite en el disco de PythonAnywhere.
  Cifrarlo requeriría SQLCipher y gestión de claves, desproporcionado frente al
  riesgo actual y al plan gratuito.
- **Sin copia de seguridad automática.** Ver `deploy/RUNBOOK.md` para el
  procedimiento manual.
- **Plan gratuito de PythonAnywhere**: la web caduca cada mes si nadie entra, el
  disco son 512 MB (~12 propuestas de 40 MB) y la salida a internet está
  restringida por lista blanca.

---

## 5. Antes de exponer el sistema a más usuarios

Por orden de importancia:

1. **Definir `API_TOKEN`.** Hoy está vacío: los identificadores de propuesta son
   consecutivos, así que sin token basta recorrer `/download/1..N` para
   descargar las propuestas de todos los clientes.
2. **Confirmar `TRUST_PROXY_COUNT`** en el entorno donde se despliegue.
3. **Programar la purga de retención** (tarea mensual) y revisar el plazo con
   el responsable comercial.
4. **Revisar el registro de auditoría** periódicamente.

---

## 6. Cómo verificarlo

```bash
python -m pytest tests/test_seguridad.py -q   # 54 comprobaciones de esta guía
pip-audit -r requirements.txt                 # vulnerabilidades en dependencias
```

Para auditar a mano un `.pptx` ya entregado:

```python
from services.pptx_privacy import inspeccionar
print(inspeccionar("ruta/al/deck.pptx"))
```
