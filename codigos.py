#!/usr/bin/env python3
"""Qué códigos publica el sitio y dónde vive cada uno.

Es la única lista: la ingesta, la construcción de páginas y el robot diario
leen de aquí. Agregar un código es agregar una línea.

  slug        carpeta y nombre de los archivos de datos
  nombre      como se llama en pantalla
  ley         qué es, para el subtítulo (se completa desde el XML si va vacío)
  id          idNorma en Ley Chile
  articulado  cuando la norma fija varios textos refundidos, cuál queremos
  carpeta     "" es la raíz del sitio; el resto son subcarpetas

El Procesal Penal se queda en la raíz a propósito: su dirección ya está
publicada y compartida, y moverla rompería los enlaces que existen.
"""

CODIGOS = [
    {
        "slug": "cpp",
        "nombre": "Código Procesal Penal",
        "corto": "CPP Chile",
        "id": 176595,
        "articulado": None,
        "carpeta": "",
    },
    {
        "slug": "penal",
        "nombre": "Código Penal",
        "corto": "Penal Chile",
        "id": 1984,
        "articulado": None,
        "carpeta": "penal",
    },
    {
        "slug": "trabajo",
        "nombre": "Código del Trabajo",
        "corto": "Trabajo Chile",
        "id": 207436,
        "articulado": None,
        "carpeta": "trabajo",
    },
    {
        "slug": "tributario",
        "nombre": "Código Tributario",
        "corto": "Tributario Chile",
        "id": 6374,
        "articulado": None,
        "carpeta": "tributario",
    },
]

POR_SLUG = {c["slug"]: c for c in CODIGOS}


def ruta_datos(codigo, extension="js"):
    """Dónde vive el archivo de datos de un código, visto desde la raíz."""
    base = f"{codigo['carpeta']}/" if codigo["carpeta"] else ""
    return f"{base}datos/{codigo['slug']}.{extension}"


def hacia_raiz(codigo):
    """El prefijo relativo para volver a la raíz desde la página del código."""
    return "../" if codigo["carpeta"] else ""
