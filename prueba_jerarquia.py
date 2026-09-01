#!/usr/bin/env python3
"""Prueba del recorrido con las formas reales que publica la BCN.

No pide nada a la red: arma XML mínimos con la misma estructura que tienen
el Código Civil, el Tributario y el Procesal Penal, y comprueba que el índice
salga como corresponde en los tres casos.
"""
import xml.etree.ElementTree as ET

import ingesta_bcn as ing

NS = "http://www.leychile.cl/esquemas"


def ef(tipo, titulo=None, texto=None, hijos=(), fecha="2020-01-01"):
    partes = []
    if titulo is not None:
        partes.append(f'<Metadatos><TituloParte presente="si">{titulo}</TituloParte></Metadatos>')
    else:
        partes.append('<Metadatos><TituloParte presente="no"> </TituloParte></Metadatos>')
    if texto is not None:
        partes.append(f"<Texto>{texto}</Texto>")
    if hijos:
        partes.append("<EstructurasFuncionales>" + "".join(hijos) + "</EstructurasFuncionales>")
    return (f'<EstructuraFuncional tipoParte="{tipo}" fechaVersion="{fecha}" '
            f'derogado="no derogado">' + "".join(partes) + "</EstructuraFuncional>")


def arbol_de(*nodos):
    xml = (f'<Norma xmlns="{NS}" fechaVersion="2025-01-01">'
           "<EstructurasFuncionales>" + "".join(nodos) + "</EstructurasFuncionales></Norma>")
    raiz = ET.fromstring(xml)
    arts = []
    cont = raiz.find(ing.Q("EstructurasFuncionales"))
    ramas = ing.recorrer(list(cont.findall(ing.Q("EstructuraFuncional"))), arts, [])
    return ramas, arts


def aplanar(ramas, prof=1):
    fuera = []
    for r in ramas:
        fuera.append((prof, r["tipo"], r["nombre"]))
        fuera += aplanar(r["hijos"], prof + 1)
    return fuera


fallos = []


def comprobar(nombre, condicion, detalle=""):
    print(("  ok   " if condicion else "  FALLA ") + nombre + (f"  {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(nombre)


# --------------------------------------------------- 1. la forma del Tributario
# Todo el código cuelga de un único nodo «Artículo» sin título, que solo sirve
# de envoltorio. Antes el recorrido se quedaba con las manos vacías.
ramas, arts = arbol_de(
    ef("Artículo", None, None, [
        ef("Libro", "Libro Primero De la administración", hijos=[
            ef("Título", "Título I Normas generales", hijos=[
                ef("Artículo", None, "Artículo 1º.- Las disposiciones de este Código."),
                ef("Artículo", None, "Artículo 2º.- En lo no previsto."),
            ]),
        ]),
        ef("Libro", "Libro Segundo De los apremios", hijos=[
            ef("Artículo", None, "Artículo 3º.- El Servicio podrá."),
        ]),
    ]))
plano = aplanar(ramas)
comprobar("Tributario: el índice ya no queda vacío", len(ramas) == 2, f"ramas={len(ramas)}")
comprobar("Tributario: los dos Libros suben al primer nivel",
          [p[1] for p in plano if p[0] == 1] == ["Libro", "Libro"])
comprobar("Tributario: el Título queda dentro del Libro",
          ("Título" in [p[1] for p in plano if p[0] == 2]))
comprobar("Tributario: no aparece el envoltorio como renglón vacío",
          all(p[2].strip() for p in plano), str([p[2] for p in plano]))
comprobar("Tributario: los tres artículos siguen apareciendo",
          [a["n"] for a in arts] == ["1", "2", "3"], str([a["n"] for a in arts]))
comprobar("Tributario: la ruta del artículo 1 conserva la jerarquía",
          arts[0]["ruta"] == ["Libro Libro Primero", "Título Título I"] or
          len(arts[0]["ruta"]) == 2, str(arts[0]["ruta"]))

# --------------------------------------------------- 2. la forma del Civil
# Varios nodos «Artículo» de primer nivel; solo algunos traen jerarquía dentro.
ramas, arts = arbol_de(
    ef("Artículo", None, "Artículo 1º.- La ley es una declaración."),
    ef("Artículo", None, None, [
        ef("Libro", "Libro I De las personas", hijos=[
            ef("Artículo", None, "Artículo 2º.- La costumbre no constituye derecho."),
        ]),
    ]),
)
comprobar("Civil: el Libro anidado llega al índice",
          [r["tipo"] for r in ramas] == ["Libro"], str([r["tipo"] for r in ramas]))
comprobar("Civil: el artículo suelto de antes del Libro no se pierde",
          [a["n"] for a in arts] == ["1", "2"], str([a["n"] for a in arts]))
comprobar("Civil: el artículo suelto no queda colgado de ninguna rama",
          arts[0]["ruta"] == [], str(arts[0]["ruta"]))

# --------------------------------------------------- 3. las enumeraciones
# En el Código Civil «Enumeración» no es una lista dentro de un artículo: es
# el párrafo «§ 1. De la ley», con TituloParte propio. Son 164 y sí van al
# índice. Se comprueba contra la forma real, no contra lo que yo supuse.
ramas, arts = arbol_de(
    ef("Título", "Título I Preliminar", hijos=[
        ef("Enumeración", "§ 1. De la ley", hijos=[
            ef("Artículo", None, "Artículo 1º.- La ley es una declaración."),
        ]),
        ef("Enumeración", "§ 2. Promulgación de la ley", hijos=[
            ef("Artículo", None, "Artículo 6º.- La ley no obliga sino una vez promulgada."),
        ]),
    ]))
comprobar("Párrafos §: entran al índice bajo su Título",
          aplanar(ramas) == [(1, "Título", "Preliminar"),
                             (2, "Enumeración", "§ 1. De la ley"),
                             (2, "Enumeración", "§ 2. Promulgación de la ley")],
          str(aplanar(ramas)))
comprobar("Párrafos §: sus artículos conservan la ruta completa",
          len(arts) == 2 and len(arts[0]["ruta"]) == 2, str(arts[0]["ruta"]))

# Un envoltorio sin título, en cambio, se atraviesa sin dejar renglón vacío.
ramas, arts = arbol_de(
    ef("Otros", None, None, [ef("Libro", "Libro I De las personas", hijos=[
        ef("Artículo", None, "Artículo 1º.- Texto."),
    ])]))
comprobar("Envoltorio sin título: se atraviesa",
          aplanar(ramas) == [(1, "Libro", "De las personas")], str(aplanar(ramas)))

# --------------------------------------------------- 4. la forma del Procesal Penal
# El control: Libros con Títulos y Párrafos, todos con título propio.
ramas, arts = arbol_de(
    ef("Libro", "Libro Primero Disposiciones generales", hijos=[
        ef("Título", "Título I Principios básicos", hijos=[
            ef("Artículo", None, "Artículo 1º.- Juicio previo. Ninguna persona podrá ser condenada."),
        ]),
    ]))
comprobar("Procesal Penal: la jerarquía de siempre no cambia",
          aplanar(ramas) == [(1, "Libro", "Disposiciones generales"),
                             (2, "Título", "Principios básicos")], str(aplanar(ramas)))
comprobar("Procesal Penal: el epígrafe se sigue separando",
          arts[0]["epi"] == "Juicio previo", arts[0]["epi"])

# --------------------------------------------------- 5. los textos refundidos
# El idNorma 172986 no es «el Código Civil»: es el DFL que fija seis textos.
def norma_con(*dobles):
    xml = (f'<Norma xmlns="{NS}" fechaVersion="2025-01-01"><EstructurasFuncionales>'
           + "".join(dobles) + "</EstructurasFuncionales></Norma>")
    return ET.fromstring(xml)


def fijador(n, que, dentro):
    return ef("Artículo", None, f"ARTICULO {n}º.- Fíjase el siguiente texto refundido de {que}.",
              [ef("Doble Articulado", None, None, dentro)])


cuerpo = [ef("Libro", "Libro I De las personas",
             hijos=[ef("Artículo", None, "Artículo 1º.- La ley es una declaración.")])]
varios = norma_con(fijador(2, "el Código Civil", cuerpo),
                   fijador(3, "la Ley sobre Registro Civil", cuerpo))

try:
    ing.elegir_articulado(varios, None)
    comprobar("Varios textos: sin elegir, se niega a adivinar", False, "no falló")
except SystemExit as e:
    comprobar("Varios textos: sin elegir, se niega a adivinar",
              "Registro Civil" in str(e) and "Código Civil" in str(e))

nodos, cual = ing.elegir_articulado(varios, "Código Civil")
comprobar("Varios textos: --articulado elige el correcto",
          "Código Civil" in cual and len(nodos) == 1, cual)
# sin_tildes normaliza y además pasa a minúsculas: la comparación es ciega a
# tildes y a mayúsculas, que es como la gente escribe en la línea de comandos.
comprobar("Varios textos: sin tildes ni mayúsculas también calza",
          "codigo civil" in ing.sin_tildes(ing.elegir_articulado(varios, "codigo civil")[1]))

uno = norma_con(fijador(1, "el Código Tributario", cuerpo))
nodos, cual = ing.elegir_articulado(uno, None)
comprobar("Un solo texto: se entra sin preguntar",
          len(nodos) == 1 and "Tributario" in cual, cual)
arts = []
ing.recorrer(nodos, arts, [])
comprobar("Un solo texto: el artículo del decreto que lo fija no se cuela",
          [a["n"] for a in arts] == ["1"], str([a["n"] for a in arts]))

# --------------------------------------------------- 6. la fecha centinela
comprobar("Fecha: 2222-02-02 se rechaza", not ing.fecha_plausible("2222-02-02"))
comprobar("Fecha: una real se acepta", ing.fecha_plausible("2025-08-28"))
comprobar("Fecha: vacía se rechaza", not ing.fecha_plausible(""))
comprobar("Fecha: basura se rechaza", not ing.fecha_plausible("sin fecha"))
comprobar("Fecha: 1874 (Código Penal) se acepta", ing.fecha_plausible("1874-11-12"))

print()
# Salir con código 0 solo si todo pasó: así el robot de GitHub se detiene
# cuando una prueba falla, en vez de seguir y publicar algo roto.
if fallos:
    raise SystemExit(f"{len(fallos)} pruebas fallaron: {fallos}")
print("todas las pruebas pasaron")
