/*
 * Pantalla principal: formulario, historial, temas y ajustes
 *
 * Extraído de templates/index.html. Vivía embebido en el HTML, lo que obligaba a
 * permitir 'unsafe-inline' en script-src de la CSP y dejaba la defensa contra
 * XSS a medias. Con el JS en un fichero propio, script-src puede ser 'self'.
 *
 * Los valores que antes inyectaba Jinja llegan ahora por atributos data-* del
 * <body>: una plantilla no puede escribir código dentro de este fichero.
 */

// Token opcional de API (cuando el servidor define API_TOKEN).
// Se configura una sola vez desde la consola del navegador:
//   localStorage.setItem('seidor_api_token', 'mi-token')
// Toggle Accordion Panel
const configToggle = document.getElementById('configToggle');
const configContent = document.getElementById('configContent');
const configArrow = document.getElementById('configArrow');

configToggle.addEventListener('click', () => {
    const abierto = configContent.style.display === 'block';
    configContent.style.display = abierto ? 'none' : 'block';
    configArrow.className = abierto ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-up';
    configToggle.setAttribute('aria-expanded', String(!abierto));
});

// Modal de Ajustes
const settingsModal = document.getElementById('settingsModal');
const openSettingsBtn = document.getElementById('openSettingsBtn');
const closeSettingsModalBtn = document.getElementById('closeSettingsModalBtn');
const cancelSettingsBtn = document.getElementById('cancelSettingsBtn');
const settingsForm = document.getElementById('settingsForm');

// anosRoi se usa para etiquetar el ROI con su horizonte real (es configurable).
let anosRoi = 5;

/**
 * Carga la configuración comercial.
 * syncProposalFields: solo en la carga inicial y tras guardar cambios.
 * Al abrir el modal NO debe sincronizarse, porque sobreescribía en
 * silencio la tarifa que el usuario había puesto para esa propuesta.
 */
function loadSystemConfig(syncProposalFields = false) {
    const aviso = document.getElementById('settingsError');
    return fetch('/api/config', { headers: authHeaders() })
        .then(res => res.json().then(data => ({ ok: res.ok, status: res.status, data })))
        .then(({ ok, status, data }) => {
            if (!ok || data.error) {
                throw new Error(data.error || `El servidor respondió ${status}.`);
            }
            if (aviso) aviso.style.display = 'none';

            const set = (id, value) => {
                const el = document.getElementById(id);
                if (el && value !== undefined && value !== null) el.value = value;
            };

            if (data.tarifa_hora_consultor) {
                set('sysConsultingRate', data.tarifa_hora_consultor.valor);
                if (syncProposalFields) set('consultingRate', data.tarifa_hora_consultor.valor);
            }
            if (data.porcentaje_ams) {
                set('sysSupportPercentage', data.porcentaje_ams.valor);
                // toFixed(1) en vez de Math.round: con 0.155 se mostraba 16
                // y la propuesta se generaba con 16% en lugar de 15,5%.
                if (syncProposalFields) {
                    set('supportPercentage', (Number(data.porcentaje_ams.valor) * 100).toFixed(1));
                }
            }
            if (data.margen_saas) set('sysSaasMargin', data.margen_saas.valor);
            if (data.anos_roi) {
                set('sysRoiYears', data.anos_roi.valor);
                anosRoi = Number(data.anos_roi.valor) || 5;
                actualizarEtiquetasRoi();
            }
            if (data.factor_igv) set('sysIgvFactor', data.factor_igv.valor);
            if (data.tipo_cambio_pen) set('sysExchangeRate', data.tipo_cambio_pen.valor);
            if (data.factor_ahorro) set('sysSavingsFactor', data.factor_ahorro.valor);
        })
        .catch(err => {
        clearTimeout(timeoutId);
        if (err && err.name === 'AbortError') {
            clearInterval(interval);
            overlay.style.display = 'none';
            submitBtn.disabled = false;
            previewBtn.disabled = false;
            showToast('La operación tardó más de 3 minutos y se canceló. Verifica que el archivo Excel del estimador no esté abierto y vuelve a intentarlo.', 'error', 12000);
            return;
        }
            // Antes esto solo iba a la consola: el modal se abría con los
            // 6 campos vacíos y required, sin poder guardar ni saber por qué.
            console.error('[config]', err);
            if (aviso) {
                aviso.textContent = 'No se pudieron cargar los ajustes: ' + err.message;
                aviso.style.display = 'block';
            }
        });
}

// El valor mostrado es roi_five_years, pero el horizonte es configurable:
// etiquetarlo evita que el comercial presente un ROI a 3 años como si
// fuera a 5 (o al revés) delante del cliente.
function actualizarEtiquetasRoi() {
    document.querySelectorAll('[data-roi-label]').forEach(el => {
        el.textContent = `Retorno de Inversión (ROI a ${anosRoi} años)`;
    });
}

openSettingsBtn.addEventListener('click', () => {
    loadSystemConfig(false);
    settingsModal.style.display = 'flex';
    settingsModal.setAttribute('aria-hidden', 'false');
    document.getElementById('sysConsultingRate')?.focus();
});

const closeModal = () => {
    settingsModal.style.display = 'none';
    settingsModal.setAttribute('aria-hidden', 'true');
    openSettingsBtn.focus();
};
closeSettingsModalBtn.addEventListener('click', closeModal);
cancelSettingsBtn.addEventListener('click', closeModal);
// Cerrar con Escape y con clic en el fondo (chatbot.html ya lo hacía).
settingsModal.addEventListener('click', (e) => {
    if (e.target === settingsModal) closeModal();
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && settingsModal.style.display === 'flex') closeModal();
});

settingsForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const payload = {
        tarifa_hora_consultor: document.getElementById('sysConsultingRate').value,
        porcentaje_ams: document.getElementById('sysSupportPercentage').value,
        margen_saas: document.getElementById('sysSaasMargin').value,
        anos_roi: document.getElementById('sysRoiYears').value,
        factor_igv: document.getElementById('sysIgvFactor').value,
        tipo_cambio_pen: document.getElementById('sysExchangeRate').value,
        factor_ahorro: document.getElementById('sysSavingsFactor').value
    };

    fetch('/api/config', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'error');
        } else {
            showToast(data.message || 'Configuración guardada correctamente.');
            closeModal();
            loadSystemConfig(true);
        }
    })
    .catch(err => {
        console.error("Error guardando config:", err);
        showToast('No se pudieron guardar los ajustes: ' + (err.message || 'error desconocido'), 'error');
    });
});

/* ------------------------------------------------------------------
 * Tema visual del deck
 *
 * El catálogo lo sirve /api/themes, así que añadir un tema en
 * services/themes.py lo hace aparecer aquí sin tocar el frontend. Lo
 * mismo con las fuentes admitidas y las claves de color: el formulario
 * de personalización se construye a partir de la respuesta para que no
 * pueda desincronizarse del backend.
 * ------------------------------------------------------------------ */
let catalogoTemas = [];
let fuentesAdmitidas = [];
let clavesColor = [];
let coloresPersonalizados = {};   // solo lo que el consultor ha tocado

const ETIQUETAS_COLOR = {
    primary: 'Cabeceras',
    royal: 'Acento intermedio',
    secondary: 'Acento y gráficos',
    background: 'Fondo de tarjetas',
    white: 'Texto sobre cabecera',
    text: 'Texto del cuerpo',
    gray: 'Texto secundario',
    card_line: 'Contorno de tarjetas'
};

function temaSeleccionado() {
    const sel = document.getElementById('deckTheme');
    return catalogoTemas.find(t => t.id === sel.value) || catalogoTemas[0];
}

/** Payload de tema para la API: un id a secas, o el objeto a medida. */
function temaParaEnviar() {
    const base = document.getElementById('deckTheme').value;
    const fuenteTitulos = document.getElementById('customFontHeading').value;
    const fuenteCuerpo = document.getElementById('customFontBody').value;
    const t = temaSeleccionado();
    const hayColores = Object.keys(coloresPersonalizados).length > 0;
    const hayFuentes = t && (fuenteTitulos !== t.fuente_titulos || fuenteCuerpo !== t.fuente_cuerpo);
    if (!hayColores && !hayFuentes) return base;
    return {
        base: base,
        colores: Object.assign({}, coloresPersonalizados),
        fuente_titulos: fuenteTitulos,
        fuente_cuerpo: fuenteCuerpo
    };
}

/** Colores efectivos = los del tema base con lo personalizado encima. */
function coloresEfectivos() {
    const t = temaSeleccionado();
    return Object.assign({}, t ? t.colores : {}, coloresPersonalizados);
}

function pintarMuestras() {
    const cont = document.getElementById('themeSwatches');
    const colores = coloresEfectivos();
    cont.innerHTML = '';
    ['primary', 'royal', 'secondary', 'background', 'text'].forEach(clave => {
        const punto = document.createElement('span');
        punto.className = 'theme-swatch';
        punto.style.background = colores[clave] || '#000';
        punto.title = `${ETIQUETAS_COLOR[clave] || clave}: ${colores[clave]}`;
        cont.appendChild(punto);
    });
}

function construirFormularioColores() {
    const grid = document.getElementById('customColorGrid');
    const colores = coloresEfectivos();
    grid.innerHTML = '';
    clavesColor.forEach(clave => {
        const fila = document.createElement('div');
        fila.className = 'custom-theme__row';
        const id = 'color_' + clave;
        fila.innerHTML = `
            <label for="${id}">${escapeHtml(ETIQUETAS_COLOR[clave] || clave)}</label>
            <input type="color" id="${id}" value="${escapeHtml(colores[clave] || '#000000')}"
                   aria-label="${escapeHtml(ETIQUETAS_COLOR[clave] || clave)}">
        `;
        const input = fila.querySelector('input');
        input.addEventListener('input', () => {
            coloresPersonalizados[clave] = input.value.toUpperCase();
            pintarMuestras();
            aplicarTemaAlPreview();
        });
        grid.appendChild(fila);
    });
}

function rellenarSelectFuentes() {
    const t = temaSeleccionado();
    [['customFontHeading', 'fuente_titulos'], ['customFontBody', 'fuente_cuerpo']].forEach(([id, clave]) => {
        const sel = document.getElementById(id);
        sel.innerHTML = '';
        fuentesAdmitidas.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f;
            opt.textContent = f;
            if (t && f === t[clave]) opt.selected = true;
            sel.appendChild(opt);
        });
    });
}

/**
 * Tiñe la previsualización con los colores elegidos, para que el
 * consultor vea el tema antes de invertir ~20 s en generar el PPTX.
 */
function aplicarTemaAlPreview() {
    const colores = coloresEfectivos();
    const card = document.getElementById('previewCard');
    if (!card) return;
    card.style.setProperty('--tema-primary', colores.primary);
    card.style.setProperty('--tema-secondary', colores.secondary);
    card.style.setProperty('--tema-background', colores.background);
    card.style.setProperty('--tema-text', colores.text);
    const t = temaSeleccionado();
    const fuente = document.getElementById('customFontBody').value || (t && t.fuente_cuerpo) || 'Arial';
    card.style.setProperty('--tema-fuente', fuente);
}

function alCambiarTema() {
    coloresPersonalizados = {};          // el tema nuevo manda
    const t = temaSeleccionado();
    document.getElementById('themeHint').textContent = t ? t.descripcion : '';
    rellenarSelectFuentes();
    construirFormularioColores();
    pintarMuestras();
    aplicarTemaAlPreview();
}

async function cargarCatalogoTemas() {
    try {
        const d = await fetchJson('/api/themes');
        catalogoTemas = d.temas || [];
        fuentesAdmitidas = d.fuentes || [];
        clavesColor = d.claves_color || [];
        const sel = document.getElementById('deckTheme');
        sel.innerHTML = '';
        catalogoTemas.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.nombre;
            if (t.id === (d.por_defecto || 'seidor')) opt.selected = true;
            sel.appendChild(opt);
        });
        alCambiarTema();
    } catch (err) {
        // Sin catálogo el formulario sigue siendo usable: se genera con
        // el tema por defecto del servidor.
        console.error('No se pudo cargar el catálogo de temas:', err);
        document.getElementById('themeHint').textContent =
            'No se pudo cargar el catálogo de temas; se usará el corporativo.';
    }
}

document.getElementById('deckTheme').addEventListener('change', alCambiarTema);

document.getElementById('toggleCustomTheme').addEventListener('click', (e) => {
    const panel = document.getElementById('customThemePanel');
    const abierto = !panel.hidden;
    panel.hidden = abierto;
    e.currentTarget.setAttribute('aria-expanded', String(!abierto));
    e.currentTarget.textContent = abierto
        ? 'Personalizar colores y tipografía'
        : 'Ocultar personalización';
});

document.getElementById('resetCustomTheme').addEventListener('click', () => {
    alCambiarTema();
    showToast('Tema restablecido a ' + (temaSeleccionado()?.nombre || 'el original') + '.');
});

cargarCatalogoTemas();

let proposalsCache = []; // Acumulado de propuestas ya cargadas
let historialOffset = 0;
let historialTotal = 0;
let historialCargando = false;

const HISTORIAL_PAGINA = 50;

const fmtMoneda = (v) => v == null
    ? '—'
    : '$ ' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtNum = (v, sufijo) => v == null ? '—' : v + sufijo;

/**
 * Lee del bullet "Facturable" del preview el importe bimoneda ya formateado.
 * Devuelve null si no lo encuentra, para que el llamador decida el respaldo.
 */
function importeFacturableDePreview(previewJson) {
    if (!Array.isArray(previewJson) || previewJson.length === 0) return null;
    // Un slide sin 'title' (guardado por una versión anterior) lanzaba
    // TypeError y hacía perder toda la tabla.
    const econSlide = previewJson.find(s => typeof s?.title === 'string' && s.title.includes("Propuesta Económica"));
    if (!econSlide || !Array.isArray(econSlide.bullets)) return null;
    const bullet = econSlide.bullets.find(b => typeof b === 'string' && b.includes("Facturable"));
    if (!bullet) return null;
    const partes = bullet.split("Facturable: ");
    return partes.length > 1 ? partes[1] : null;
}

function actualizarDashboard(latest) {
    // Un total_investment nulo (fila antigua o generación interrumpida)
    // lanzaba TypeError y hacía perder TODO el historial mostrando un
    // "error de conexión" falso aunque el servidor hubiera respondido bien.
    let displayInvestment = fmtMoneda(latest.total_investment);
    const facturable = importeFacturableDePreview(latest.preview_json);
    if (facturable) {
        const costParts = facturable.split(" / ");
        displayInvestment = costParts.length > 1
            ? `${escapeHtml(costParts[0])}<span class="cell-secondary">${escapeHtml(costParts[1])}</span>`
            : escapeHtml(facturable);
    }
    document.getElementById('dashboardInvestment').innerHTML = displayInvestment;
    document.getElementById('dashboardWeeks').innerText = fmtNum(latest.total_weeks, ' Semanas');
    document.getElementById('dashboardRoi').innerText = fmtNum(latest.roi_five_years, ' %');
    document.getElementById('dashboardPayback').innerText = fmtNum(latest.payback_period, ' Años');
}

function crearFilaHistorial(prop) {
    const tr = document.createElement('tr');
    tr.dataset.rowId = prop.id;

    const compBadge = prop.complexity === 'Alta'
        ? `<span class="badge badge-alta">Alta</span>`
        : `<span class="badge badge-media">Media</span>`;

    const editionBadge = prop.edition === 'Private'
        ? `<span class="badge badge-private" title="RISE with SAP">Private</span>`
        : `<span class="badge badge-public" title="GROW with SAP">Public</span>`;

    // Misma protección que en el dashboard: hay filas antiguas
    // (o de generaciones interrumpidas) con total_investment NULL,
    // y sin el guard un solo registro tumbaba toda la tabla.
    let tableInvStr = prop.total_investment == null
        ? '—'
        : '$ ' + Number(prop.total_investment).toLocaleString('en-US', { maximumFractionDigits: 0 });
    const facturable = importeFacturableDePreview(prop.preview_json);
    if (facturable) {
        tableInvStr = facturable.replace(/\.00/g, ''); // decimales fuera para la vista corta
    }

    const safeName = escapeHtml(prop.company_name);
    const safeSector = escapeHtml(prop.sector || '-');
    tr.innerHTML = `
        <td>
            <button type="button" class="link-button" data-preview-id="${prop.id}" title="Haz clic para previsualizar">
                ${safeName}
            </button>
        </td>
        <td>${compBadge}</td>
        <td>${editionBadge}</td>
        <td>${safeSector}</td>
        <td>${escapeHtml(tableInvStr)}</td>
        <td>${fmtNum(prop.total_weeks, ' sem')}</td>
        <td>${fmtNum(prop.roi_five_years, ' %')}</td>
        <td>
            <div class="row-actions">
                <button type="button" class="btn-download" data-download-id="${prop.id}">
                    <i class="fa-solid fa-cloud-arrow-down" aria-hidden="true"></i> Descargar
                </button>
                <button type="button" class="btn-row-delete" data-delete-id="${prop.id}"
                        title="Eliminar del historial"
                        aria-label="Eliminar la propuesta de ${safeName}">
                    <i class="fa-solid fa-trash-can" aria-hidden="true"></i>
                </button>
            </div>
        </td>
    `;
    tr.querySelector('[data-preview-id]').addEventListener('click', () => {
        viewHistoricalPreview(prop.id);
    });
    tr.querySelector('[data-delete-id]').addEventListener('click', () => {
        eliminarPropuesta(prop.id, prop.company_name);
    });
    // Descarga por fetch (no <a href>) para poder mandar el token.
    const btnDescarga = tr.querySelector('[data-download-id]');
    btnDescarga.addEventListener('click', async () => {
        btnDescarga.disabled = true;
        try {
            await descargarArchivo('/download/' + prop.id);
        } finally {
            btnDescarga.disabled = false;
        }
    });
    return tr;
}

function actualizarPieHistorial() {
    const pie = document.getElementById('historyFooter');
    const contador = document.getElementById('historyCount');
    const boton = document.getElementById('btnLoadMore');
    if (!pie || !contador || !boton) return;
    if (historialTotal === 0) {
        pie.hidden = true;
        return;
    }
    pie.hidden = false;
    contador.textContent = hayFiltrosActivos()
        ? `Mostrando ${proposalsCache.length} de ${historialTotal} coincidencias`
        : `Mostrando ${proposalsCache.length} de ${historialTotal} propuestas`;
    boton.hidden = proposalsCache.length >= historialTotal;
    boton.disabled = historialCargando;
}

/**
 * Filtros activos del historial, como query string.
 *
 * El filtrado se hace en el SERVIDOR, no sobre proposalsCache: la caché solo
 * tiene las páginas ya descargadas, así que filtrar en el navegador dejaría
 * fuera propuestas que sí cumplen el criterio pero viven en páginas todavía
 * no cargadas — justo el caso que motiva tener buscador con cientos de filas.
 */
function filtrosDelHistorial() {
    const partes = [];
    const termino = document.getElementById('buscarHistorial')?.value.trim();
    if (termino) partes.push('q=' + encodeURIComponent(termino));
    const complejidad = document.getElementById('filtroComplejidad')?.value;
    if (complejidad) partes.push('complejidad=' + encodeURIComponent(complejidad));
    const edicion = document.getElementById('filtroEdicion')?.value;
    if (edicion) partes.push('edicion=' + encodeURIComponent(edicion));
    const dias = document.getElementById('filtroAntiguedad')?.value;
    if (dias) partes.push('dias=' + encodeURIComponent(dias));
    return partes.length ? '&' + partes.join('&') : '';
}

function hayFiltrosActivos() {
    return filtrosDelHistorial() !== '';
}

/** Un filtro nuevo reinicia la paginación: empieza por la primera página. */
function aplicarFiltros() {
    const boton = document.getElementById('limpiarFiltros');
    if (boton) boton.hidden = !hayFiltrosActivos();
    fetchHistory();
}

// Se espera a que el consultor deje de teclear: sin esto saldría una petición
// por pulsación y el limitador cortaría a mitad de una palabra.
let temporizadorBusqueda = null;
document.getElementById('buscarHistorial')?.addEventListener('input', () => {
    clearTimeout(temporizadorBusqueda);
    temporizadorBusqueda = setTimeout(aplicarFiltros, 350);
});

['filtroComplejidad', 'filtroEdicion', 'filtroAntiguedad'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', aplicarFiltros);
});

document.getElementById('limpiarFiltros')?.addEventListener('click', () => {
    document.getElementById('buscarHistorial').value = '';
    ['filtroComplejidad', 'filtroEdicion', 'filtroAntiguedad']
        .forEach(id => { document.getElementById(id).value = ''; });
    aplicarFiltros();
});

/**
 * Carga el historial paginado. Con cientos de propuestas, traerlas todas
 * de golpe (con su preview_json) llegaba a varios MB y bloqueaba el render.
 * @param {boolean} anexar - true para añadir la siguiente página.
 */
async function fetchHistory(anexar = false) {
    if (historialCargando) return;
    historialCargando = true;
    const tbody = document.getElementById('historyTableBody');
    if (!anexar) {
        historialOffset = 0;
        proposalsCache = [];
    }
    actualizarPieHistorial();

    try {
        const res = await fetch(`/api/proposals?limit=${HISTORIAL_PAGINA}&offset=${historialOffset}${filtrosDelHistorial()}`, {
            headers: authHeaders()
        });
        const data = await res.json();
        if (!Array.isArray(data)) {
            throw new Error(data && data.error ? data.error : 'Respuesta inesperada del servidor.');
        }
        // Si la cabecera falta (un proxy que la filtre), se asume que lo
        // recibido es todo para no ofrecer un "Cargar más" que no avanza.
        const totalCabecera = parseInt(res.headers.get('X-Total-Count'), 10);
        historialTotal = Number.isFinite(totalCabecera)
            ? totalCabecera
            : (anexar ? proposalsCache.length + data.length : data.length);

        if (!anexar) {
            tbody.innerHTML = '';
            if (data.length === 0) {
                tbody.innerHTML = hayFiltrosActivos()
                    ? `
                    <tr>
                        <td colspan="8" class="table-state">
                            Ninguna propuesta coincide con la búsqueda.
                        </td>
                    </tr>
                    `
                    : `
                    <tr>
                        <td colspan="8" class="table-state">
                            Aún no hay propuestas. Completa el formulario y pulsa
                            <strong>Generar PPTX</strong> para crear la primera.
                        </td>
                    </tr>
                    `;
                ['dashboardInvestment', 'dashboardWeeks', 'dashboardRoi', 'dashboardPayback']
                    .forEach(id => {
                        const el = document.getElementById(id);
                        if (el) el.textContent = '—';
                    });
                historialTotal = 0;
                return;
            }
            actualizarDashboard(data[0]);
        }

        const fragmento = document.createDocumentFragment();
        data.forEach(prop => fragmento.appendChild(crearFilaHistorial(prop)));
        tbody.appendChild(fragmento);

        proposalsCache = proposalsCache.concat(data);
        historialOffset = proposalsCache.length;
    } catch (err) {
        console.error("Error loading history:", err);
        if (!anexar) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="table-state table-state--error">
                        Error al conectar con el servidor local.
                    </td>
                </tr>
            `;
            historialTotal = 0;
        } else {
            showToast('No se pudieron cargar más propuestas: ' + (err.message || 'error desconocido'), 'error');
        }
    } finally {
        historialCargando = false;
        actualizarPieHistorial();
    }
}

document.getElementById('btnLoadMore').addEventListener('click', () => fetchHistory(true));

function viewHistoricalPreview(id) {
    const prop = proposalsCache.find(p => p.id === id);
    if (prop && prop.preview_json && prop.preview_json.length > 0) {
        renderPreviewDeck(prop.preview_json);
    } else {
        showToast('Esta propuesta no cuenta con datos de previsualización.', 'error');
    }
}

/**
 * Elimina una propuesta del historial (y su PPTX en el servidor).
 * Antes no existía forma de hacerlo: una propuesta generada por error
 * contaminaba el panel de métricas de forma permanente.
 */
async function eliminarPropuesta(id, nombre) {
    if (!confirm(`¿Eliminar la propuesta de "${nombre}" del historial? Se borrará también su archivo PPTX.`)) return;
    try {
        const data = await fetchJson('/api/proposals/' + id, { method: 'DELETE' });
        if (data.success) {
            showToast(data.message || 'Propuesta eliminada.');
            // Se quita solo la fila borrada. Recargar el historial
            // completo devolvía al usuario a la primera página de 50:
            // borrar la propuesta 380 le hacía perder todo el listado
            // que había cargado.
            const fila = document.querySelector(`#historyTableBody tr[data-row-id="${id}"]`);
            const eraLaPrimera = proposalsCache.length > 0 && proposalsCache[0].id === id;
            if (fila) fila.remove();
            proposalsCache = proposalsCache.filter(p => p.id !== id);
            historialTotal = Math.max(0, historialTotal - 1);
            historialOffset = proposalsCache.length;

            if (proposalsCache.length === 0 || eraLaPrimera) {
                // El dashboard refleja la propuesta más reciente: si esa
                // es la que se ha borrado, hay que volver a pedirla.
                fetchHistory();
            } else {
                actualizarPieHistorial();
            }
        } else {
            showToast(data.error || 'No se pudo eliminar la propuesta.', 'error');
        }
    } catch (err) {
        showToast(err.message || 'No se pudo eliminar la propuesta.', 'error');
    }
}

// --- Cajón lateral (móvil) ---
const hamburgerBtn = document.getElementById('hamburgerBtn');
// Clase explícita en vez de '.container > div:first-child': ese selector
// estructural rompía el menú en silencio al reordenar el contenedor.
const sidebar = document.getElementById('formSidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const drawerCloseBtn = document.getElementById('drawerCloseBtn');

function abrirCajon(abrir) {
    if (!sidebar || !sidebarOverlay) return;
    sidebar.classList.toggle('show-sidebar', abrir);
    sidebarOverlay.classList.toggle('show', abrir);
    if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', String(abrir));
    if (abrir) {
        sidebar.querySelector('input, select, button')?.focus();
    } else if (hamburgerBtn) {
        hamburgerBtn.focus();
    }
}

if (hamburgerBtn && sidebar && sidebarOverlay) {
    hamburgerBtn.addEventListener('click', () => {
        abrirCajon(!sidebar.classList.contains('show-sidebar'));
    });
    sidebarOverlay.addEventListener('click', () => abrirCajon(false));
    drawerCloseBtn?.addEventListener('click', () => abrirCajon(false));

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sidebar.classList.contains('show-sidebar')) {
            abrirCajon(false);
        }
    });

    // Si se agranda la ventana con el cajón abierto, el layout vuelve a
    // dos columnas pero el overlay se quedaba encima bloqueando la UI.
    window.addEventListener('resize', () => {
        if (window.innerWidth >= 768 && sidebar.classList.contains('show-sidebar')) {
            abrirCajon(false);
        }
    });
}

// Form Submit & Preview Actions
const form = document.getElementById('proposalForm');

/**
 * Muestra las advertencias del motor financiero (ROI negativo, payback
 * fuera del horizonte). Son para el consultor: nunca van al PPTX del
 * cliente, pero evitan enviar una propuesta imposible de defender.
 */
function mostrarAdvertencias(avisos) {
    const box = document.getElementById('advisoryBox');
    const list = document.getElementById('advisoryList');
    if (!box || !list) return;
    list.innerHTML = '';
    if (!Array.isArray(avisos) || avisos.length === 0) {
        box.style.display = 'none';
        return;
    }
    avisos.forEach(a => {
        const li = document.createElement('li');
        li.textContent = a;
        list.appendChild(li);
    });
    box.style.display = 'block';
}
const previewBtn = document.getElementById('previewBtn');

const runPreviewOrGenerate = (isGenerate) => {
    // "Previsualizar" es type="button", así que no disparaba la validación
    // nativa: los min/max de los campos numéricos solo se comprobaban al
    // generar. reportValidity() cubre ambos caminos y muestra los globos
    // del navegador junto al campo, en vez de un error 400 del servidor.
    if (!form.reportValidity()) return;

    const companyName = document.getElementById('companyName').value.trim();
    if (!companyName) {
        showToast('Ingresa el nombre de la empresa.', 'error');
        return;
    }

    const submitBtn = document.getElementById('submitBtn');
    const overlay = document.getElementById('loadingOverlay');
    const loadText = document.getElementById('loadingText');
    const progressBarFill = document.getElementById('progressBarFill');

    // Cerrar menú lateral en móviles al iniciar acción
    if (sidebar) {
        sidebar.classList.remove('show-sidebar');
    }
    if (sidebarOverlay) {
        sidebarOverlay.classList.remove('show');
    }

    submitBtn.disabled = true;
    previewBtn.disabled = true;
    overlay.style.display = 'flex';

    // Reset loading stepper elements
    const stepsIds = ['step1', 'step2', 'step3', 'step4'];
    const originalIcons = ['fa-magnifying-glass', 'fa-gears', 'fa-coins', 'fa-file-powerpoint'];
    stepsIds.forEach((id, idx) => {
        const el = document.getElementById(id);
        if (el) {
            el.className = 'loading-step';
            const icon = el.querySelector('i');
            if (icon) icon.className = 'fa-solid ' + originalIcons[idx] + ' step-icon';
        }
    });
    progressBarFill.style.width = '10%';

    // Stepper simulation config
    const stepStates = isGenerate ? [
        { text: "Investigando huella digital (Scraping)...", active: 'step1', completed: [], width: '25%' },
        { text: "Analizando complejidad y presencia local...", active: 'step2', completed: ['step1'], width: '50%' },
        { text: "Procesando cálculos y lectura de Excel...", active: 'step3', completed: ['step1', 'step2'], width: '75%' },
        { text: "Inyectando datos y gráficos nativos en PowerPoint...", active: 'step4', completed: ['step1', 'step2', 'step3'], width: '90%' }
    ] : [
        { text: "Investigando huella digital (Scraping)...", active: 'step1', completed: [], width: '30%' },
        { text: "Analizando complejidad técnica...", active: 'step2', completed: ['step1'], width: '60%' },
        { text: "Generando previsualización estructural JSON...", active: 'step3', completed: ['step1', 'step2'], width: '85%' }
    ];

    let currentStepIdx = 0;
    const updateStepperUI = (idx) => {
        const state = stepStates[idx];
        loadText.innerText = state.text;
        progressBarFill.style.width = state.width;

        stepsIds.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            if (id === state.active) {
                el.className = 'loading-step active';
            } else if (state.completed.includes(id)) {
                el.className = 'loading-step completed';
                const icon = el.querySelector('i');
                if (icon) icon.className = 'fa-solid fa-circle-check step-icon';
            } else {
                el.className = 'loading-step';
            }
        });
    };

    updateStepperUI(0);
    const interval = setInterval(() => {
        if (currentStepIdx < stepStates.length - 1) {
            currentStepIdx++;
            updateStepperUI(currentStepIdx);
        }
    }, 2500);

    const payload = {
        company_name: companyName,
        sector: document.getElementById('companySector').value,
        annual_revenue: document.getElementById('annualRevenue').value,
        complexity_mode: document.getElementById('complexityMode').value,
        edition: document.getElementById('sapEdition').value,
        theme: temaParaEnviar(),
        consulting_rate: document.getElementById('consultingRate').value,
        support_percentage: document.getElementById('supportPercentage').value,
        modular_licenses: {
            FI: document.getElementById('licFI').value,
            CO: document.getElementById('licCO').value,
            MM: document.getElementById('licMM').value,
            SD: document.getElementById('licSD').value,
            PP: document.getElementById('licPP').value,
            PS: document.getElementById('licPS').value
        }
    };

    const endpoint = isGenerate ? '/api/generate' : '/api/preview';

    // Sin timeout, si el scraping o la generación se colgaban el overlay
    // bloqueaba la pantalla indefinidamente y la única salida era recargar.
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 180000);

    fetch(endpoint, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
        body: JSON.stringify(payload),
        signal: controller.signal
    })
    .then(res => { clearTimeout(timeoutId); return res.json(); })
    .then(data => {
        clearInterval(interval);

        // Finalize loading steps visually before closing
        progressBarFill.style.width = '100%';
        stepsIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.className = 'loading-step completed';
                const icon = el.querySelector('i');
                if (icon) icon.className = 'fa-solid fa-circle-check step-icon';
            }
        });

        setTimeout(() => {
            overlay.style.display = 'none';
            submitBtn.disabled = false;
            previewBtn.disabled = false;

            if (data.error) {
                showToast(data.error, 'error');
            } else {
                // El historial primero: si el render del preview fallaba,
                // la propuesta ya generada no aparecía en la tabla y
                // parecía que había fallado.
                if (isGenerate) {
                    fetchHistory();
                    // Solo se limpia la empresa: el resto del contexto
                    // (licencias, sector, tarifas, edición) se conserva
                    // para poder generar variantes del mismo cliente.
                    document.getElementById('companyName').value = '';
                    document.getElementById('companyName').focus();
                }
                mostrarAdvertencias(data.advertencias);
                try {
                    renderPreviewDeck(data.slides_preview);
                } catch (e) {
                    console.error('[preview]', e);
                    showToast('La propuesta se generó correctamente, pero no se pudo mostrar la previsualización.', 'error');
                }
            }
        }, 500);
    })
    .catch(err => {
        clearInterval(interval);
        overlay.style.display = 'none';
        submitBtn.disabled = false;
        previewBtn.disabled = false;
        showToast(err.message || 'Ocurrió un error en el servidor local.', 'error');
    });
};

previewBtn.addEventListener('click', () => runPreviewOrGenerate(false));
form.addEventListener('submit', (e) => {
    e.preventDefault();
    runPreviewOrGenerate(true);
});

// Previsualización Carrusel/Tabs de Diapositivas
let activeSlides = [];

function renderPreviewDeck(slides) {
    const previewCard = document.getElementById('previewCard');
    const previewTabs = document.getElementById('previewTabs');

    // Antes retornaba en silencio: el usuario pulsaba "Previsualizar",
    // el overlay corría sus pasos, se cerraba y no pasaba nada.
    if (!Array.isArray(slides) || slides.length === 0) {
        previewCard.style.display = 'none';
        showToast('No se pudo generar la previsualización de la propuesta.', 'error');
        return;
    }
    activeSlides = slides;

    previewCard.style.display = 'block';
    previewTabs.innerHTML = '';

    slides.forEach((slide, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        // Clases en vez de style.cssText: así las media queries de
        // style.css pueden ajustar la pestaña en móvil.
        btn.className = 'preview-tab' + (idx === 0 ? ' active' : '');
        btn.textContent = `Diapositiva ${slide.num}`;
        btn.setAttribute('role', 'tab');
        btn.setAttribute('aria-selected', idx === 0 ? 'true' : 'false');
        btn.setAttribute('aria-label', `Diapositiva ${slide.num}: ${slide.title || ''}`);

        btn.addEventListener('click', () => {
            Array.from(previewTabs.children).forEach(child => {
                child.classList.remove('active');
                child.setAttribute('aria-selected', 'false');
            });
            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
            showMockSlide(slide);
        });

        previewTabs.appendChild(btn);
    });

    showMockSlide(slides[0]);
    scrollSuave(previewCard);
}

function showMockSlide(slide) {
    document.getElementById('mockTitle').innerText = slide.title;
    document.getElementById('mockSubtitle').innerText = slide.subtitle;
    document.getElementById('mockSlideNum').innerText = slide.num;

    const bulletsUl = document.getElementById('mockBullets');
    bulletsUl.innerHTML = '';

    slide.bullets.forEach(bullet => {
        const li = document.createElement('li');
        li.style.marginBottom = '0.5rem';
        li.textContent = bullet;
        bulletsUl.appendChild(li);
    });
}

// Initialize Page
function iniciarApp() {
    fetchHistory();
    // true: en el arranque sí se sincronizan los campos del formulario
    // con la configuración global guardada.
    loadSystemConfig(true);
}

// El <script src> va al final de <body>, así que el DOM ya está listo.
// Si algún día pasa a un fichero externo con defer, DOMContentLoaded ya
// habría disparado y la app arrancaría vacía sin ningún error visible.
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciarApp);
} else {
    iniciarApp();
}
