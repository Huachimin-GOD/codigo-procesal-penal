#!/usr/bin/env python3
"""Arma la página de cada código a partir de shell.html.

shell.html se edita como fragmento con marcadores ({{NOMBRE}}, {{ARTICULOS}}…).
Este script lo envuelve en un documento HTML completo, rellena los marcadores y
engancha el archivo de datos que corresponde.

El envoltorio no es decorativo: sin <!doctype> el navegador entra en modo
compatibilidad (quirks), y sin lang="es-CL" la partición de palabras no
funciona y los lectores de pantalla leen el español con fonética inglesa.

La cantidad de artículos y la fecha salen del JSON ya generado, no de la mano:
así los metadatos de la página no pueden quedar desfasados del contenido.

    python3 construir.py            # todos los códigos que tengan datos
    python3 construir.py penal      # solo uno
"""
import json
import pathlib
import sys

from codigos import CODIGOS, SITIO, hacia_raiz, ruta_datos

RAIZ = pathlib.Path(__file__).parent
BASE_PUBLICA = "https://australcode-1.github.io/codigo-procesal-penal/"


def datos_de(codigo):
    """Cantidad de artículos y fecha, leídos del JSON generado por la ingesta."""
    ruta = SITIO / ruta_datos(codigo, "json")
    if not ruta.exists():
        return None
    d = json.loads(ruta.read_text(encoding="utf-8"))
    return {
        "articulos": len(d["articulos"]),
        "fecha": d.get("ultimaVersion", ""),
        "etiqueta": ("última modificación incorporada al"
                     if d.get("versionInferida") else "texto refundido al"),
        "ley": d.get("ley", ""),
    }


def cresta(nombre):
    """El nombre partido en dos renglones para el escudo del índice."""
    palabras = nombre.split()
    if len(palabras) < 3:
        return "<br>".join(palabras)
    corte = len(palabras) // 2 + len(palabras) % 2
    return " ".join(palabras[:corte]) + "<br>" + " ".join(palabras[corte:])


def selector(actual):
    """Los enlaces para saltar de un código a otro."""
    raiz = hacia_raiz(actual)
    partes = []
    for c in CODIGOS:
        if not (SITIO / ruta_datos(c, "json")).exists():
            continue  # todavía no tiene datos: no se ofrece un enlace roto
        destino = f"{raiz}{c['carpeta']}/" if c["carpeta"] else (raiz or "./")
        if c["slug"] == actual["slug"]:
            partes.append(f'<span class="cod-actual" aria-current="page">{c["nombre"]}</span>')
        else:
            partes.append(f'<a href="{destino}">{c["nombre"]}</a>')
    if len(partes) < 2:
        return ""
    return ('<nav class="codigos" aria-label="Otros códigos">'
            + "".join(partes) + "</nav>")


def ficha(codigo, info, base):
    """Datos estructurados: qué es esta página, para un buscador.

    Sin esto un buscador ve una página de texto y tiene que adivinar. Con esto
    sabe que es una ley chilena, cuál, de qué fecha, y que el sitio se puede
    buscar desde «?q=». Se arma aquí y no en shell.html porque los valores ya
    están leídos del JSON: así la ficha no puede contradecir a la página.
    """
    grafo = [
        {
            "@type": "Legislation",
            "name": f"{codigo['nombre']} de Chile",
            "alternateName": codigo["nombre"],
            "legislationIdentifier": info["ley"],
            "legislationType": "Código",
            "legislationJurisdiction": {"@type": "Country", "name": "Chile"},
            "inLanguage": "es-CL",
            "url": base,
            "dateModified": info["fecha"],
            "isBasedOn": f"https://www.bcn.cl/leychile/navegar?idNorma={codigo['id']}",
            "sourceOrganization": {
                "@type": "Organization",
                "name": "Biblioteca del Congreso Nacional de Chile",
                "url": "https://www.bcn.cl/leychile",
            },
            "description": (f"Los {info['articulos']} artículos del {codigo['nombre']} "
                            f"({info['ley']}), {info['etiqueta']} {info['fecha']}."),
        },
        {
            "@type": "WebSite",
            "name": f"{codigo['nombre']} de Chile",
            "url": base,
            "inLanguage": "es-CL",
            "potentialAction": {
                "@type": "SearchAction",
                "target": {"@type": "EntryPoint", "urlTemplate": base + "?q={consulta}"},
                "query-input": "required name=consulta",
            },
        },
    ]
    texto = json.dumps({"@context": "https://schema.org", "@graph": grafo},
                       ensure_ascii=False, indent=1)
    # «</» dentro de un <script> cerraría la etiqueta antes de tiempo
    texto = texto.replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{texto}\n</script>\n'


def indice_del_sitio(construidos):
    """robots.txt y sitemap.xml.

    El sitemap es la lista de las páginas con su fecha: es lo que se entrega
    en Search Console para que el buscador sepa qué hay y cuándo cambió.
    """
    urls = []
    for codigo, info in construidos:
        base = BASE_PUBLICA + (f"{codigo['carpeta']}/" if codigo["carpeta"] else "")
        urls.append("  <url>\n"
                    f"    <loc>{base}</loc>\n"
                    f"    <lastmod>{info['fecha']}</lastmod>\n"
                    "    <changefreq>weekly</changefreq>\n"
                    "  </url>")
    mapa = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")
    (SITIO / "sitemap.xml").write_text(mapa, encoding="utf-8")

    # Aviso honesto: en GitHub Pages el robots.txt que los buscadores leen es
    # el de la raíz del dominio, no el de este subdirectorio. Se deja igual
    # porque no estorba y queda correcto si algún día hay dominio propio; el
    # sitemap se entrega a mano en Search Console.
    (SITIO / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {BASE_PUBLICA}sitemap.xml\n", encoding="utf-8")
    return len(urls)


def construir(codigo):
    info = datos_de(codigo)
    if info is None:
        return None

    fragmento = (RAIZ / "shell.html").read_text(encoding="utf-8")
    corte = fragmento.index("</style>") + len("</style>")
    cabeza, cuerpo = fragmento[:corte], fragmento[corte:]

    raiz_rel = hacia_raiz(codigo)
    base = BASE_PUBLICA + (f"{codigo['carpeta']}/" if codigo["carpeta"] else "")

    # el archivo de datos se carga antes del script del lector
    archivo_datos = f"datos/{codigo['slug']}.js"
    cuerpo = cuerpo.replace('<script>\nconst store',
                            f'<script src="{archivo_datos}"></script>\n<script>\nconst store', 1)

    # el selector de códigos, justo después del escudo del índice. Si hay un
    # solo código no se dibuja nada, y tampoco se altera el espaciado.
    sel = selector(codigo)
    if sel:
        cuerpo = cuerpo.replace('<nav class="side-scroll" id="tree"',
                                sel + '\n    <nav class="side-scroll" id="tree"', 1)

    salto = '<a class="salto" href="#doc">Saltar al articulado</a>\n'
    documento = (
        "<!doctype html>\n"
        '<html lang="es-CL">\n'
        "<head>\n" + cabeza.strip() + "\n"
        + ficha(codigo, info, base) +
        "</head>\n"
        "<body>\n" + salto + cuerpo.strip() + "\n"
        "</body>\n"
        "</html>\n"
    )

    for marca, valor in {
        "{{NOMBRE}}": codigo["nombre"],
        "{{NOMBRE_CRESTA}}": cresta(codigo["nombre"]),
        "{{CORTO}}": codigo["corto"],
        "{{LEY}}": info["ley"],
        "{{IDNORMA}}": str(codigo["id"]),
        "{{ARTICULOS}}": str(info["articulos"]),
        "{{FECHA}}": info["fecha"],
        "{{ETIQUETA_FECHA}}": info["etiqueta"],
        "{{BASE}}": base,
        "{{RAIZ}}": raiz_rel,
    }.items():
        documento = documento.replace(marca, valor)

    if "{{" in documento:
        resto = documento[documento.index("{{"):][:40]
        sys.exit(f"quedó un marcador sin rellenar: {resto}")

    carpeta = SITIO / codigo["carpeta"] if codigo["carpeta"] else SITIO
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / "index.html"
    destino.write_text(documento, encoding="utf-8")

    manifiesto(codigo, info, carpeta, raiz_rel)
    trabajador(codigo, carpeta)

    for necesario in ("<!doctype html>", 'lang="es-CL"', "<head>", "<body>",
                      archivo_datos, 'class="salto"', "<meta charset",
                      'type="application/ld+json"', "<title>"):
        if necesario not in documento:
            sys.exit(f"FALTA en {codigo['slug']}: {necesario}")

    return destino, len(documento), info


def manifiesto(codigo, info, carpeta, raiz_rel):
    m = {
        "name": f"{codigo['nombre']} de Chile",
        "short_name": codigo["corto"],
        "description": (f"Lector del {codigo['nombre']} ({info['ley']}) generado desde el "
                        f"XML oficial de Ley Chile. Sitio no oficial."),
        "lang": "es-CL", "dir": "ltr",
        "start_url": ".", "scope": ".",
        "display": "standalone", "orientation": "portrait-primary",
        "background_color": "#FAF8F4", "theme_color": "#FAF8F4",
        "categories": ["books", "education", "reference"],
        "icons": [
            {"src": f"{raiz_rel}iconos/icono-192.png", "sizes": "192x192",
             "type": "image/png", "purpose": "any"},
            {"src": f"{raiz_rel}iconos/icono-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "any"},
            {"src": f"{raiz_rel}iconos/icono-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
    }
    (carpeta / "manifest.webmanifest").write_text(
        json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def trabajador(codigo, carpeta):
    """Cada código lleva su propio service worker, con su propia caché.

    Si compartieran caché, actualizar un código invalidaría los demás.
    """
    plantilla = (RAIZ / "sw-plantilla.js").read_text(encoding="utf-8")
    (carpeta / "sw.js").write_text(
        plantilla.replace("{{CACHE}}", f"{codigo['slug']}-v3"), encoding="utf-8")


def main():
    pedidos = sys.argv[1:]
    hechos = []
    for c in CODIGOS:
        if pedidos and c["slug"] not in pedidos:
            continue
        r = construir(c)
        if r is None:
            print(f"  ·  {c['slug']}: sin datos todavía, se omite", file=sys.stderr)
            continue
        destino, largo, info = r
        print(f"{destino.relative_to(RAIZ)} · {largo:,} caracteres · "
              f"{info['articulos']} artículos · {info['fecha']}")
        hechos.append((c, info))
    if not hechos:
        sys.exit("no se construyó ninguna página")

    # El sitemap enumera todo lo publicado, no solo lo que se acaba de armar:
    # un sitemap parcial le diría al buscador que las demás páginas ya no están.
    todos = []
    for c in CODIGOS:
        info = datos_de(c)
        if info and (SITIO / c["carpeta"] / "index.html").exists():
            todos.append((c, info))
    print(f"sitemap.xml con {indice_del_sitio(todos)} páginas · robots.txt")
    print("estructura verificada")


if __name__ == "__main__":
    main()
