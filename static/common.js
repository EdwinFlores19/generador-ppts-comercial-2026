/*
 * common.js — utilidades compartidas por index.html y chatbot.html
 *
 * Antes escapeHtml(), authHeaders() y el patrón de fetch estaban duplicados
 * literalmente en las dos plantillas (con implementaciones que ya habían
 * divergido: una envolvía en String() y la otra no), y el sistema de toast solo
 * existía en el chatbot mientras index.html usaba alert() del navegador.
 */

/** Escapa texto para insertarlo con innerHTML de forma segura. */
function escapeHtml(unsafe) {
    if (unsafe === null || unsafe === undefined) return '';
    return String(unsafe)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

/**
 * Token opcional de API (cuando el servidor define API_TOKEN).
 * Se configura una sola vez desde la consola del navegador:
 *   localStorage.setItem('seidor_api_token', 'mi-token')
 */
function authHeaders() {
    try {
        const token = localStorage.getItem('seidor_api_token');
        return token ? { 'Authorization': 'Bearer ' + token } : {};
    } catch (e) {
        // localStorage puede lanzar en modo privado o con cookies bloqueadas.
        return {};
    }
}

/**
 * fetch + JSON con mensajes de error accionables para el usuario final.
 * No muta el objeto de opciones recibido.
 */
async function fetchJson(url, options = {}) {
    const opts = Object.assign({}, options, {
        headers: Object.assign({}, authHeaders(), options.headers || {})
    });

    let res;
    try {
        res = await fetch(url, opts);
    } catch (netErr) {
        if (netErr && netErr.name === 'AbortError') throw netErr;
        throw new Error('Error de red. Verifica tu conexión al servidor.');
    }

    if (res.status === 401) {
        throw new Error('No autorizado. Configura tu token con localStorage.setItem("seidor_api_token", "…").');
    }

    const text = await res.text();
    if (!text) {
        throw new Error('El servidor respondió vacío. Intenta de nuevo.');
    }

    try {
        return JSON.parse(text);
    } catch (parseErr) {
        console.error('fetchJson: respuesta no-JSON de', url, ':', text.slice(0, 300));
        if (res.status >= 500) {
            throw new Error('Error interno del servidor (' + res.status + ').');
        }
        throw new Error('Respuesta inesperada del servidor.');
    }
}

/**
 * Descarga un archivo del servidor enviando la cabecera Authorization.
 *
 * Un <a href="/download/1"> es una navegación del navegador y no puede llevar
 * cabeceras, así que con API_TOKEN definido devolvía un 401 en blanco. Aquí se
 * baja por fetch y se entrega al usuario desde un blob.
 *
 * @param {string} url  Ruta del archivo en el servidor.
 * @param {string} [nombreSugerido]  Nombre por defecto si el servidor no manda uno.
 * @returns {Promise<boolean>} true si la descarga se disparó.
 */
async function descargarArchivo(url, nombreSugerido) {
    let res;
    try {
        res = await fetch(url, { headers: authHeaders() });
    } catch (netErr) {
        showToast('Error de red al descargar el archivo.', 'error');
        return false;
    }

    if (res.status === 401) {
        showToast('No autorizado. Configura tu token con localStorage.setItem("seidor_api_token", "…").', 'error');
        return false;
    }
    if (!res.ok) {
        showToast('No se pudo descargar el archivo (' + res.status + ').', 'error');
        return false;
    }

    // El nombre real viene en Content-Disposition; se usa cuando está.
    let nombre = nombreSugerido || 'propuesta.pptx';
    const disposition = res.headers.get('Content-Disposition') || '';
    const coincidencia = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
    if (coincidencia) {
        try {
            nombre = decodeURIComponent(coincidencia[1]);
        } catch (e) {
            nombre = coincidencia[1];
        }
    }

    const blob = await res.blob();
    const enlace = document.createElement('a');
    enlace.href = URL.createObjectURL(blob);
    enlace.download = nombre;
    document.body.appendChild(enlace);
    enlace.click();
    document.body.removeChild(enlace);
    // Sin revoke, un PPTX de ~38 MB se queda retenido en memoria por descarga.
    setTimeout(() => URL.revokeObjectURL(enlace.href), 30000);
    return true;
}

/* --- Sistema de notificaciones (toast) --- */
let __toastTimer = null;

/**
 * Muestra una notificación no bloqueante.
 * @param {string} msg  Texto a mostrar.
 * @param {'success'|'error'} [type]  'error' pinta el toast en rojo.
 * @param {number} [ms]  Duración; los errores duran más por defecto.
 */
function showToast(msg, type, ms) {
    let toast = document.getElementById('toast');
    if (!toast) {
        // index.html no tenía contenedor de toast: se crea al primer uso.
        toast = document.createElement('div');
        toast.id = 'toast';
        toast.className = 'toast';
        toast.setAttribute('role', 'status');
        toast.setAttribute('aria-live', 'polite');
        document.body.appendChild(toast);
    }

    const icono = type === 'error' ? 'circle-exclamation' : 'circle-check';
    toast.className = 'toast show' + (type ? ' ' + type : '');
    toast.innerHTML = '<i class="fa-solid fa-' + icono + '" aria-hidden="true"></i> '
        + '<span>' + escapeHtml(msg) + '</span>';

    // El timer se cancela: dos toasts seguidos se cortaban entre sí porque el
    // temporizador del primero ocultaba el segundo.
    clearTimeout(__toastTimer);
    const duracion = ms || (type === 'error' ? 7000 : 4000);
    __toastTimer = setTimeout(() => toast.classList.remove('show'), duracion);
}

/** true si el usuario pidió movimiento reducido en su sistema operativo. */
function prefiereMovimientoReducido() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** scrollIntoView que respeta prefers-reduced-motion. */
function scrollSuave(el, opciones) {
    if (!el) return;
    el.scrollIntoView(Object.assign(
        { behavior: prefiereMovimientoReducido() ? 'auto' : 'smooth' },
        opciones || {}
    ));
}
