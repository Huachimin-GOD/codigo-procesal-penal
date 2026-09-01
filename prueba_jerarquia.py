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

# --------------------------------------------------- 8. la fecha centinela
comprobar("Fecha: 2222-02-02 se rechaza", not ing.fecha_plausible("2222-02-02"))
comprobar("Fecha: una real se acepta", ing.fecha_plausible("2025-08-28"))
comprobar("Fecha: vacía se rechaza", not ing.fecha_plausible(""))
comprobar("Fecha: basura se rechaza", not ing.fecha_plausible("sin fecha"))
comprobar("Fecha: 1874 (Código Penal) se acepta", ing.fecha_plausible("1874-11-12"))

# --------------------------------------------------- 6. la numeración
# Todos los encabezados de aquí abajo están copiados del XML de la BCN, no
# inventados. Cada uno rompía la numeración de una manera distinta.
CASOS = [
    # (encabezado tal como lo publica la BCN, número esperado, de qué código)
    ("Artículo 1º.- Juicio previo.",              "1",        "Procesal Penal"),
    ("Artículo 226 A.- Autorización judicial.",   "226 A",    "Procesal Penal"),
    ("Art. 2º. En lo no previsto.",               "2",        "Civil"),
    ("ART. 3. Los delitos, atendida su gravedad", "3",        "Penal"),
    ("ART. 32. BIS La imposición del presidio",   "32 bis",   "Penal"),
    ("ART. 297. BIS Cuando las amenazas",         "297 bis",  "Penal"),
    ("ART. 161 - A. Se castigará con la pena",    "161 A",    "Penal"),
    ("ART. 161-B. Se castigará con la pena",      "161 B",    "Penal"),
    ("Artículo 313° a. El que, careciendo",       "313 a",    "Penal"),
    ("ART. 319 a). Derogado.",                    "319 a",    "Penal"),
    ("Artículo 4° bis.- Las obligaciones",        "4 bis",    "Tributario"),
    ("Artículo 4º ter.- Los hechos imponibles",   "4 ter",    "Tributario"),
    ("Art. 1o Las disposiciones de este Código",  "1",        "del Trabajo"),
    ("Artículo 1.o Las relaciones laborales",     "1",        "del Trabajo"),
    ("Artículo 10.o De los contratos",            "10",       "del Trabajo"),
    # El Código del Trabajo agrega tres formas más, todas del XML real.
    ("Artículo 313° c Las penas señaladas",       "313 c",    "Penal"),
    ("ART. 483. a) El contador o cualquiera",     "483 a",    "Penal"),
    ("Artículo 152 quáter Ñ.- El trabajador",     "152 quáter Ñ",     "del Trabajo"),
    ("Artículo 152 quáter O bis.- El empleador",  "152 quáter O bis", "del Trabajo"),
    ("Artículo 152 quáter O ter.- La obligación", "152 quáter O ter", "del Trabajo"),
    ("Artículo 152 quinquies A.- Del aviso",      "152 quinquies A",  "del Trabajo"),
    ("Artículo 183-Ñ.- Podrá celebrarse",         "183 Ñ",    "del Trabajo"),
    ("Artículo 183-AA.- La usuaria que contrate", "183 AA",   "del Trabajo"),
    # Y los que NO deben tocarse: una mayúscula suelta es el inicio del texto.
    ("ART. 5. El que matare a otro",              "5",        "Penal"),
    ("ART. 313. El que, sin hallarse autorizado", "313",      "Penal"),
    ("ART. 483. Se presume responsable",          "483",      "Penal"),
]

for encabezado, esperado, codigo in CASOS:
    num, epi, cuerpo = ing.partir_articulo([encabezado])
    comprobar(f"{codigo}: «{encabezado[:34]}…» → {esperado}",
              num == esperado, f"dio «{num}»")

# La «o» de «Art. 1o» es marca de ordinal, no la primera letra del texto.
num, epi, cuerpo = ing.partir_articulo(["Art. 1o Las disposiciones de este Código no alteran."])
comprobar("del Trabajo: la «o» del ordinal no se cuela en el texto",
          cuerpo and cuerpo[0].startswith("Las disposiciones"), str(cuerpo))

# El 32 y el 32 bis son artículos distintos y no deben chocar.
comprobar("Penal: el 32 y el 32 bis no colisionan",
          ing.partir_articulo(["ART. 32. La pena de presidio sujeta al condenado."])[0] == "32"
          and ing.partir_articulo(["ART. 32. BIS La imposición del presidio."])[0] == "32 bis")

# Y el 32 bis se ordena justo después del 32, no en cualquier parte.
comprobar("Penal: el 32 bis va después del 32 y antes del 33",
          ing.orden("32") < ing.orden("32 bis") < ing.orden("33"),
          f"{ing.orden('32')} < {ing.orden('32 bis')} < {ing.orden('33')}")
comprobar("Penal: el 161 A va después del 161 y antes del 161 B",
          ing.orden("161") < ing.orden("161 A") < ing.orden("161 B"),
          f"{ing.orden('161')} < {ing.orden('161 A')} < {ing.orden('161 B')}")
comprobar("del Trabajo: el «O bis» cae entre el «O» y el «P»",
          ing.orden("152 quáter O") < ing.orden("152 quáter O bis")
          < ing.orden("152 quáter O ter") < ing.orden("152 quáter P"))
comprobar("del Trabajo: «183 AA» va después de «183 Z», no antes",
          ing.orden("183 Z") < ing.orden("183 AA") < ing.orden("183 AB"))
comprobar("del Trabajo: la Ñ va entre la N y la O, como en español",
          ing.orden("183 N") < ing.orden("183 Ñ") < ing.orden("183 O"))

# --------------------------------------------------- 7. los transitorios
# El articulado transitorio vuelve a numerar desde 1. La BCN lo marca con un
# atributo propio; sin usarlo, el Tributario tendría dos artículos «1».
def ef_trans(tipo, texto, transitorio):
    marca = "transitorio" if transitorio else "no transitorio"
    return (f'<EstructuraFuncional tipoParte="{tipo}" fechaVersion="2020-01-01" '
            f'derogado="no derogado" transitorio="{marca}">'
            f'<Metadatos><TituloParte presente="no">\u00a0</TituloParte></Metadatos>'
            f"<Texto>{texto}</Texto></EstructuraFuncional>")


xml = (f'<Norma xmlns="{NS}" fechaVersion="2025-01-01"><EstructurasFuncionales>'
       + ef_trans("Artículo", "Artículo 1.- Las disposiciones de este Código.", False)
       + ef_trans("Artículo", "Artículo 2.- En lo no previsto.", False)
       + ef_trans("Artículo", "Artículo 1°.- Las normas contenidas en el inciso 2°.", True)
       + ef_trans("Artículo", "Artículo 2°.- Los términos que hubieren empezado a correr.", True)
       + "</EstructurasFuncionales></Norma>")
raiz = ET.fromstring(xml)
arts = []
cont = raiz.find(ing.Q("EstructurasFuncionales"))
ing.recorrer(list(cont.findall(ing.Q("EstructuraFuncional"))), arts, [])
nums = [a["n"] for a in arts]
comprobar("Tributario: los transitorios no chocan con los permanentes",
          nums == ["1", "2", "1 transitorio", "2 transitorio"], str(nums))
comprobar("Tributario: ningún número se repite",
          len(nums) == len(set(nums)), str(nums))
comprobar("Tributario: el articulado transitorio va al final",
          ing.orden("2") < ing.orden("1 transitorio"),
          f"{ing.orden('2')} < {ing.orden('1 transitorio')}")
comprobar("Tributario: el texto del transitorio queda intacto",
          arts[2]["p"] and arts[2]["p"][0].startswith("Las normas contenidas"),
          str(arts[2]["p"]))

# El «Artículo transitorio» sin número del Procesal Penal no se duplica la palabra.
xml2 = (f'<Norma xmlns="{NS}" fechaVersion="2025-01-01"><EstructurasFuncionales>'
        + ef_trans("Artículo", "Artículo transitorio.- Reglas para la aplicación de las penas.", True)
        + "</EstructurasFuncionales></Norma>")
arts2 = []
r2 = ET.fromstring(xml2).find(ing.Q("EstructurasFuncionales"))
ing.recorrer(list(r2.findall(ing.Q("EstructuraFuncional"))), arts2, [])
comprobar("Procesal Penal: «Artículo transitorio» no queda «transitorio transitorio»",
          [a["n"] for a in arts2] == ["transitorio"], str([a["n"] for a in arts2]))

print()
# Salir con código 0 solo si todo pasó: así el robot de GitHub se detiene
# cuando una prueba falla, en vez de seguir y publicar algo roto.
if fallos:
    raise SystemExit(f"{len(fallos)} pruebas fallaron: {fallos}")
print("todas las pruebas pasaron")
