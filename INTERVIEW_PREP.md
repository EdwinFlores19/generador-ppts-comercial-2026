# 🏆 Baluarte de Entrevistas y Sustentación Técnica: *Grow Deck Automator*

Esta guía contiene las preguntas y respuestas técnicas más desafiantes y minuciosas que un Arquitecto de Software Senior o un Jurado de Tesis haría sobre la arquitectura e implementación de la suite **Grow Deck Automator**.

---

## 🏛️ Preguntas y Respuestas Técnicas (Q&A)

### 1. Concurrencia y Persistencia de Datos en SQLite
> [!IMPORTANT]
> **Pregunta:** ¿Cómo garantizó que SQLite no sufriera bloqueos (`database is locked`) durante un test de estrés con hilos concurrentes en Flask?

**Respuesta:**  
SQLite es un motor de base de datos extraordinariamente rápido y robusto para lecturas concurrentes, pero aplica un bloqueo a nivel de archivo entero durante operaciones de escritura (bloqueo exclusivo). En un servidor web multihilo como Flask, múltiples peticiones simultáneas intentando escribir al mismo tiempo pueden generar el error `sqlite3.OperationalError: database is locked`.

Para solventarlo con total resiliencia, implementamos tres estrategias combinadas en el backend:
1. **Administradores de Contexto Seguro (`with`):** En lugar de mantener una conexión global abierta, creamos y cerramos conexiones de forma dinámica y efímera utilizando bloques de contexto:
   ```python
   with closing(get_db_connection()) as conn:
       with conn: # Transacción atómica
           # Operaciones de lectura o escritura
   ```
   El uso de `contextlib.closing` garantiza que la conexión se libere de inmediato al terminar el bloque, devolviendo los recursos al sistema operativo.
2. **Transacciones Atómicas Delimitadas (`with conn`):** En SQLite, cuando se ingresa a un bloque `with conn`, el driver de Python inicia automáticamente una transacción (`BEGIN TRANSACTION`). Si el bloque finaliza con éxito, realiza un `COMMIT` automático; si ocurre una excepción, ejecuta un `ROLLBACK`. Esto minimiza la ventana de tiempo en la que la base de datos se encuentra bloqueada para escritura.
3. **Busy Timeout Ajustado:** Al establecer la conexión en `get_db_connection`, se define un parámetro de tiempo de espera (`timeout=10.0`). Esto indica a SQLite que, si encuentra la base de datos ocupada por otra escritura, el hilo actual no fallará de inmediato, sino que esperará (haciendo pooling interno) hasta 10 segundos para que se libere el bloqueo.

---

### 2. Manipulación XML de PowerPoint con python-pptx
> [!IMPORTANT]
> **Pregunta:** ¿Cómo inyectó gráficos nativos de Office y limpió las diapositivas del PowerPoint base sin romper el 'Slide Master' o los logotipos institucionales de Seidor?

**Respuesta:**  
El reto consistía en no generar una presentación vacía desde cero, sino utilizar una plantilla corporativa existente (`Capacitación de Joule - El futuro de SAP.pptx`) que ya contenía toda la identidad visual (Slide Masters, guías tipográficas, logos, paleta de colores y layouts). 

Para lograrlo de forma quirúrgica sin romper el contenedor XML `.pptx`, implementamos:
1. **Limpieza Quirúrgica del Historial de Diapositivas:**  
   En python-pptx, las diapositivas son elementos ordenados dentro de una lista XML llamada `_sldIdLst`. Iteramos en reversa (desde la última diapositiva a la primera) para eliminar de forma segura los nodos sin alterar el índice de las diapositivas restantes. También desvinculamos las relaciones físicas de los archivos XML (`prs.part.drop_rel(rId)`), dejando la plantilla limpia pero con los Slide Masters cargados en memoria:
   ```python
   id_list = prs.slides._sldIdLst
   for i in range(len(id_list) - 1, -1, -1):
       slide_id = id_list[i]
       rId = slide_id.rId
       prs.part.drop_rel(rId)
       del id_list[i]
   ```
2. **Preservación y Vinculación de Slide Masters:**  
   Para crear nuevas láminas, no usamos lienzos en blanco. Buscamos mediante palabras clave (`find_layout_by_keywords`) los layouts predefinidos del master original (ej: "portada", "blanca"). Así, heredamos automáticamente logos, números de página, fondos de marca y tipografías corporativas preestablecidas.
3. **Inyección de Gráficos XML Nativo de Office:**  
   En lugar de insertar imágenes PNG de gráficos pregenerados (que se pixelan y no son editables), empleamos `CategoryChartData` y `slide.shapes.add_chart()`. Esto inyecta componentes OLE XML nativos dentro del paquete ZIP del archivo PowerPoint. Al abrir la presentación en Microsoft PowerPoint o PowerPoint Web, el usuario puede dar clic derecho sobre el gráfico circular (Pie Chart) o de columnas (Column Chart), presionar "Editar datos" y modificar los números directamente en una ventana integrada de Excel, manteniendo la calidad vectorial en cualquier resolución.

---

### 3. Implementación de Telemetría FinOps para Control de IA
> [!IMPORTANT]
> **Pregunta:** ¿Cómo se estructuró la persistencia de logs para auditar el costo exacto por consulta y el consumo de tokens en la suite?

**Respuesta:**  
El control de costes en la nube (FinOps) es crucial al desplegar aplicaciones integradas con modelos de Inteligencia Artificial (SAP Joule / DuckDuckGo Scraper / OpenAI / Azure OpenAI). En el sistema, estructuramos esto en tres niveles:
1. **Auditoría de Inversión de Negocio:** La tabla `proposals` persiste de manera desagregada la inversión en licencias (`licensing_cost`), consultoría de preventa (`consulting_cost`), soporte post-go-live (`support_cost`) e inversión neta/total facturable con el 18% de IGV. Esto permite a la gerencia de preventas calcular el ROI exacto que la suite está generando frente al costo del proyecto.
2. **Monitoreo de Latencia y Consumo API (Joule Optimizer / Scraper):**  
   Cada llamada del scraper y del optimizador de Joule es interceptada registrando:
   - Tiempo de inicio y fin de la ejecución (latencia en milisegundos).
   - Cantidad de reintentos acumulados por políticas de backoff.
   - Código HTTP de respuesta del endpoint de IA.
3. **Control de Tokens Extensible (FinOps Schema):**  
   Aunque el optimizador local de Joule corre bajo reglas heurísticas, el sistema está diseñado para que, al migrar al modelo productivo de LLM en la nube (SAP AI Core o OpenAI API), se integre la biblioteca `tiktoken` (para modelos GPT) o se lea directamente la estructura `usage` de la respuesta JSON del LLM:
   ```json
   "usage": {
       "prompt_tokens": 124,
       "completion_tokens": 56,
       "total_tokens": 180
   }
   ```
   Estos datos de tokens se registran de forma atómica en una tabla de auditoría `ai_token_logs` (vinculada por clave foránea a la propuesta), multiplicando el uso por la tarifa vigente por millón de tokens para obtener un reporte mensual consolidado de FinOps.

---

### 4. Resiliencia y Control de Bloqueos de Archivos en Windows
> [!IMPORTANT]
> **Pregunta:** ¿Cómo maneja el sistema la excepción en caso de que un usuario en Windows tenga el Excel de estimaciones (`Estimador S0 V2.0.xlsx`) abierto de forma exclusiva?

**Respuesta:**  
En sistemas operativos Windows, cuando un usuario abre una hoja de cálculo con Microsoft Excel, la aplicación bloquea el archivo para escritura exclusiva y a veces impide la lectura a procesos externos a través de un descriptor exclusivo (`File Lock`). Si el servidor Flask intenta leerlo directamente con pandas u openpyxl, se lanzará una excepción `PermissionError: [Errno 13] Permission denied`.

Para evitar la caída del sistema ante este dolor real de preventa en red, implementamos un mecanismo de **Copia Temporal en Caliente (Hot-Copy Fallback)**:
1. **Intercepción del Error de Permisos:**  
   En `financial_engine.py`, la carga del libro está envuelta en un bloque `try-except`. Si falla la apertura por bloqueo, se captura el error.
2. **Copia de Flujo de Bytes en Caliente:**  
   Utilizamos la función `shutil.copy2(EXCEL_PATH, temp_path)` apuntando a una ruta temporal del sistema (`C:\Users\ejuni\.gemini\antigravity\brain\...`). En Windows, a pesar del bloqueo del descriptor del archivo por parte de Excel, el sistema operativo permite copiar el flujo físico de datos a otra ubicación de disco.
3. **Carga desde el Archivo Espejo:**  
   El motor financiero lee la copia temporal `temp_estimador.xlsx` sin ningún bloqueo activo, procesando la información financiera con total precisión.
4. **Traducción de Errores Amigable:**  
   Si incluso la copia fallara (por ejemplo, si el archivo está corrupto o fue eliminado de la red), la API de Flask intercepta el error `OSError` en `app.py` y lo traduce a un mensaje en español amigable para la UI: *"El archivo de presupuesto 'Estimador S0 V2.0.xlsx' está bloqueado por otro usuario. Por favor, asegúrese de que el archivo Excel esté cerrado y vuelva a intentarlo."* en vez de arrojar un críptico error 500.
5. **Cierre de Descriptores:**  
   Se utiliza un bloque `finally` o llamados explícitos `wb.close()` para asegurar que no se mantengan manejadores de archivos abiertos en memoria que agoten los recursos del sistema.
