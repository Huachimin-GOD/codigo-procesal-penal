/* Trabajador de servicio: permite usar el lector sin conexión.
 *
 * Regla de oro para un sitio de leyes: el texto de la norma NUNCA se sirve
 * desde la caché si hay red. Primero se pide a la red y solo si falla se
 * recurre a la copia guardada. Así nadie lee un artículo desactualizado
 * teniendo señal, y quien está sin señal igual puede trabajar.
 */

const CACHE = 'cpp-v2';

// Lo mínimo para que el sitio arranque sin conexión.
const BASE = [
  './',
  './index.html',
  './datos/cpp.js',
  './iconos/icono-192.png',
  './iconos/icono-512.png',
];

self.addEventListener('install', evento => {
  evento.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(BASE))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())   // si algo no se puede guardar, seguimos igual
  );
});

self.addEventListener('activate', evento => {
  evento.waitUntil(
    caches.keys()
      .then(claves => Promise.all(claves.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

/** Red primero, caché como red de seguridad. Para el contenido que cambia. */
async function redPrimero(peticion) {
  try {
    const respuesta = await fetch(peticion);
    if (respuesta && respuesta.ok) {
      const cache = await caches.open(CACHE);
      cache.put(peticion, respuesta.clone());
    }
    return respuesta;
  } catch (e) {
    const guardada = await caches.match(peticion);
    if (guardada) return guardada;
    if (peticion.mode === 'navigate') {
      const inicio = await caches.match('./index.html');
      if (inicio) return inicio;
    }
    throw e;
  }
}

/** Caché primero. Para lo que no cambia: iconos y tipografías. */
async function cachePrimero(peticion) {
  const guardada = await caches.match(peticion);
  if (guardada) return guardada;
  const respuesta = await fetch(peticion);
  try {
    const cache = await caches.open(CACHE);
    cache.put(peticion, respuesta.clone());
  } catch (e) { /* respuestas opacas de otro origen: no siempre se pueden guardar */ }
  return respuesta;
}

self.addEventListener('fetch', evento => {
  const peticion = evento.request;
  if (peticion.method !== 'GET') return;

  const url = new URL(peticion.url);
  const propio = url.origin === self.location.origin;

  // Las estadísticas nunca se guardan en caché: si se guardaran, el contador
  // devolvería la respuesta vieja y dejaría de registrar visitas.
  if (url.hostname.endsWith('goatcounter.com') || url.hostname.endsWith('zgo.at')) return;

  // El documento y los datos de la ley: siempre lo más nuevo que haya.
  if (peticion.mode === 'navigate' || (propio && url.pathname.includes('/datos/'))) {
    evento.respondWith(redPrimero(peticion));
    return;
  }

  // Tipografías e iconos: no cambian, se sirven de la caché.
  if (!propio || url.pathname.includes('/iconos/')) {
    evento.respondWith(cachePrimero(peticion));
    return;
  }

  evento.respondWith(redPrimero(peticion));
});
