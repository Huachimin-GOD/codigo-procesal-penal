# Código Procesal Penal de Chile

Lector del Código Procesal Penal (Ley 19.696) construido sobre el XML oficial
de [Ley Chile](https://www.bcn.cl/leychile/navegar?idNorma=176595), de la
Biblioteca del Congreso Nacional.

**Este sitio no es oficial.** Para efectos legales rige el texto publicado por
la BCN. Cada página indica la fecha de la versión sobre la que fue generada.

## Cómo funciona

| Archivo | Qué hace |
|---|---|
| `index.html` | El lector completo: buscador, índice, notas. No contiene datos. |
| `datos/cpp.js` | Los 562 artículos. Es lo único que cambia cuando la ley cambia. |
| `datos/cpp.json` | Los mismos datos, para reutilizarlos desde otros programas. |
| `ingesta_bcn.py` | Convierte el XML de la BCN en los dos archivos anteriores. |
| `.github/workflows/actualizar.yml` | Revisa la BCN cada mañana y publica solo si hubo cambios. |
| `_headers` | Cabeceras de seguridad que aplica Cloudflare Pages. |

## Ver el sitio en tu computador

Haz doble clic en `index.html`. No hay compilación ni servidor: los cambios se
ven al guardar y recargar.

## Actualizar los datos a mano

```
python3 ingesta_bcn.py 176595 -o datos/cpp.json --js datos/cpp.js
```

Otras normas: Código Penal `1984`, Código Civil `172986`, Código del Trabajo `207436`.

## Fuente

Biblioteca del Congreso Nacional de Chile — Ley Chile.
Revisa sus condiciones de uso antes de reutilizar este contenido.
