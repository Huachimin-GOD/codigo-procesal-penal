#!/usr/bin/env python3
"""
Ingesta de normas chilenas desde el XML oficial de Ley Chile (BCN).

Convierte cualquier norma (código, ley, decreto) en el JSON que consume el lector.

Uso:
    python3 ingesta_bcn.py 176595 -o cpp.json              # descarga y convierte
    python3 ingesta_bcn.py 176595 --xml cpp.xml -o cpp.json  # desde un XML ya guardado
    python3 ingesta_bcn.py 176595 --fecha 2023-01-01       # texto vigente a esa fecha

Endpoint público y gratuito:
    https://www.bcn.cl/leychile/consulta/obtxml?opt=7&idNorma=<ID>

Esquema real del XML (EsquemaIntercambioNorma-v1-0):
    Norma > EstructurasFuncionales > EstructuraFuncional[tipoParte]
      · cada nodo tiene <Texto>, <Metadatos><TituloParte>, y anida hijos
        dentro de su propio <EstructurasFuncionales>
      · tipoParte: Libro | Título | Párrafo | Capítulo | Artículo | ...
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

NS = {"l": "http://www.leychile.cl/esquemas"}
Q = lambda t: f"{{{NS['l']}}}{t}"
ENDPOINT = "https://www.bcn.cl/leychile/consulta/obtxml?opt=7&idNorma={id}"

ROMANO = "IVXLCDM"
ORDINALES = {
    "primero": 1, "segundo": 2, "tercero": 3, "cuarto": 4, "quinto": 5,
    "sexto": 6, "séptimo": 7, "septimo": 7, "octavo": 8, "noveno": 9, "décimo": 10,
}


# ---------------------------------------------------------------- descarga

def descargar(id_norma, fecha=None, intentos=4, espera=30):
    """Descarga el XML de una norma, con reintentos ante limitación de la BCN.

    La BCN responde 429 (demasiadas peticiones) si se le piden varias normas
    seguidas: medido en la práctica, la primera pasa y la siguiente ya se
    rechaza. Por eso se espera y se reintenta con pausas crecientes, y se
    respeta la cabecera Retry-After cuando viene.
    """
    url = ENDPOINT.format(id=id_norma)
    if fecha:
        url += f"&fechaVersion={fecha}"
    # Un agente identificable y con contacto: si molestamos, que sepan a quién escribir.
    req = urllib.request.Request(url, headers={
        "User-Agent": "ingesta-leyes/2.0 (+https://github.com/australcode-1/codigo-procesal-penal)",
        "Accept": "application/xml",
    })

    ultimo = None
    for intento in range(1, intentos + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            ultimo = e
            if e.code not in (429, 503) or intento == intentos:
                raise
            pausa = int(e.headers.get("Retry-After") or 0) or espera * intento
            print(f"    la BCN respondió {e.code}; espero {pausa}s "
                  f"(intento {intento} de {intentos})", file=sys.stderr, flush=True)
            time.sleep(pausa)
        except urllib.error.URLError as e:
            ultimo = e
            if intento == intentos:
                raise
            print(f"    error de red ({e.reason}); espero {espera}s", file=sys.stderr, flush=True)
            time.sleep(espera)
    raise ultimo


# ---------------------------------------------------------------- utilidades

def sanear(crudo: bytes) -> bytes:
    """Repara los U+FFFD que la propia BCN publica dentro del XML.

    En la Ley 19.696 son diez, todos la 'o' de '-ciones' (Notificaciones,
    Resoluciones, Instrucciones). Se corrigen por patrón, no por posición.
    """
    return crudo.replace("ci\ufffdnes".encode(), b"ciones")



def incisos_de(nodo):
    """Los incisos del <Texto> de un nodo, ya limpios."""
    txt = nodo.find(Q("Texto"))
    if txt is None:
        return []
    crudo = "".join(txt.itertext()).replace("\r", "\n")
    # El XML trae los saltos de línea duros del texto impreso: una línea que
    # empieza con espacios abre un inciso nuevo; las demás continúan el anterior.
    partes = []
    for linea in crudo.split("\n"):
        if not linea.strip():
            continue
        if re.match(r"^\s", linea) or not partes:
            partes.append(linea.strip())
        else:
            partes[-1] += " " + linea.strip()
    return [re.sub(r"\s+", " ", p).strip() for p in partes if p.strip()]


def fecha_plausible(f):
    """¿Es una fecha real y no un centinela de la BCN?

    La BCN publica `2222-02-02` como fecha de la raíz en varios códigos (el
    Civil y el Penal, entre otros): no es la fecha de la versión, es su marca
    interna de «sin término». Mostrarla en el pie diría que el texto está
    refundido al año 2222.
    """
    if not f or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", f):
        return False
    return 1800 <= int(f[:4]) <= time.gmtime().tm_year + 1


# Los tipos de parte que estructuran un código. Todo lo demás que no sea un
# artículo (Enumeración, Doble Articulado, el preámbulo de promulgación) es
# envoltorio: se atraviesa sin dejar rastro en el índice.
TIPOS_ESTRUCTURA = {
    "libro", "título", "titulo", "capítulo", "capitulo", "párrafo", "parrafo",
    "parágrafo", "paragrafo", "sección", "seccion", "subsección", "subseccion",
    "parte", "subtítulo", "subtitulo", "anexo", "apéndice", "apendice",
}


def titulo_de(nodo):
    meta = nodo.find(Q("Metadatos"))
    if meta is None:
        return ""
    for etiqueta in ("TituloParte", "NombreParte"):
        el = meta.find(Q(etiqueta))
        if el is not None and el.get("presente") == "si" and (el.text or "").strip():
            return re.sub(r"\s+", " ", el.text).strip()
    return ""


def partir_cabecera(titulo, tipo):
    """'Título I Principios básicos' -> ('I', 'Principios básicos')."""
    pat = rf"^\s*{tipo}\s+([\wº°]+(?:\s+(?:bis|ter))?)\s*[.\-–]?\s*(.*)$"
    m = re.match(pat, titulo, re.IGNORECASE)
    if m:
        return m.group(1).strip(" .-"), m.group(2).strip()
    return "", titulo.strip()


# «Artículo 1º.-», «Art. 2º.», «ART. 3.» — las tres formas conviven en los
# códigos chilenos según la época en que se redactaron.
#
# El número puede venir seguido de un sufijo, y la BCN lo escribe de cinco
# maneras distintas según el código y el año. Todas están tomadas del XML real:
#
#     ART. 32. BIS        el sufijo latino después del punto  (Penal)
#     Artículo 4° bis.-   el sufijo latino pegado al número   (Tributario)
#     ART. 161 - A.       una letra separada por guion        (Penal)
#     Artículo 313° a.    una letra en minúscula              (Penal)
#     ART. 319 a).        una letra con paréntesis            (Penal)
#     Artículo 226 A.-    una letra separada por espacio      (Procesal Penal)
#
# Si alguna no se reconoce, el sufijo se pierde y el artículo choca con el
# artículo base: el 32 bis del Código Penal quedaría como un segundo «32».
NUMERO_ARTICULO = (
    r"\d+"                                    # el número
    r"(?:[º°]|o(?=[\s.,\-–]))?"                # marca de ordinal: 1º, 1°, 1o
    r"(?:\s*[.\-–]?\s*"                       # sufijo latino, con o sin punto delante
    r"(?:bis|ter|qu[aá]ter|quinquies|sexies|septies|octies|nonies|decies))?"
    r"(?:\s*[-–]?\s*[A-Za-z](?=\s*[).\-–]|\s*$))?"   # sufijo de una letra
)

RX_ART = re.compile(
    r"^\s*(?:art[íi]culos?|arts?)\.?\s*"
    r"(" + NUMERO_ARTICULO + r")"
    r"\s*[.\-–]*\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)

# «Artículo transitorio.-» y «Artículo final»: sin número, pero son artículos.
RX_ART_SIN_NUMERO = re.compile(
    r"^\s*(?:art[íi]culos?|arts?)\.?\s+(transitorio|final|[úu]nico)\b\s*[.\-–]*\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)


SUFIJOS_LATINOS = ("bis", "ter", "quater", "quáter", "quinquies", "sexies",
                   "septies", "octies", "nonies", "decies")


def normaliza_num(n):
    """Deja todas las formas en una sola: «32 bis», «161 A», «313 a».

    Sin esto, «ART. 32. BIS» y «Artículo 32 bis» serían dos artículos distintos
    en el mismo código, y ninguno de los dos se encontraría al buscar el otro.
    """
    n = n.replace("º", "").replace("°", "")
    n = re.sub(r"^(\d+)o\b", r"\1", n)        # «1o» es «1º» escrito sin el símbolo
    n = re.sub(r"[.\-–]", " ", n)               # el punto y el guion solo separan
    n = re.sub(r"\s+", " ", n).strip()
    partes = n.split(" ")
    if len(partes) > 1 and partes[1].lower() in SUFIJOS_LATINOS:
        partes[1] = partes[1].lower()           # el sufijo latino siempre en minúscula
    return " ".join(partes)


def partir_articulo(incisos):
    """Devuelve (numero, epigrafe, cuerpo[])."""
    if not incisos:
        return "", "", []
    m = RX_ART.match(incisos[0])
    if not m:
        sn = RX_ART_SIN_NUMERO.match(incisos[0])
        if sn:
            etiqueta = sn.group(1).lower().replace("unico", "único")
            resto = sn.group(2).strip()
            epi = ""
            m2 = re.match(r"^([^.]{3,150}?)\.\s*(?=[A-ZÁÉÍÓÚÑ¿“\"(])(.*)$", resto, re.DOTALL)
            if m2:
                epi, resto = m2.group(1).strip(), m2.group(2).strip()
            return etiqueta, epi, ([resto] if resto else []) + incisos[1:]
        return "", "", incisos
    num = normaliza_num(m.group(1))
    resto = m.group(2).strip()
    epi = ""
    # El epígrafe oficial es la frase inicial que cierra en punto antes del texto.
    m2 = re.match(r"^([^.]{3,150}?)\.\s*(?=[A-ZÁÉÍÓÚÑ¿“\"(])(.*)$", resto, re.DOTALL)
    if m2 and not re.search(r"\b(art|inc|N|Nº|D\.F\.L|D\.L|Sr)\.?$", m2.group(1)):
        epi, resto = m2.group(1).strip(), m2.group(2).strip()
    cuerpo = ([resto] if resto else []) + incisos[1:]
    return num, epi, cuerpo


def orden(num):
    # El articulado transitorio va después de todo el permanente, aunque sus
    # números vuelvan a empezar en 1.
    n = num.lower()
    desplazamiento = 0.0
    if n.endswith(" transitorio"):
        desplazamiento = 1e6
        n = n[: -len(" transitorio")]
    if n in ("transitorio", "final", "único"):
        return 2e6 + {"transitorio": 1, "único": 2, "final": 3}[n]
    m = re.match(r"^(\d+)(?:\s*(bis|ter|qu[aá]ter|quinquies|sexies|septies|octies|nonies|decies))?"
                 r"(?:\s*([A-Za-z]))?$", n, re.IGNORECASE)
    if not m:
        return 0.0
    return desplazamiento + _orden_base(m)


def _orden_base(m):
    sufijos = {"bis": .1, "ter": .2, "quater": .3, "quáter": .3, "quinquies": .4,
               "sexies": .5, "septies": .6, "octies": .7, "nonies": .8, "decies": .9}
    s = (m.group(2) or "").lower()
    letra = (m.group(3) or "").upper()
    extra = (ord(letra) - 64) / 1000 if letra else 0.0
    return float(m.group(1)) + sufijos.get(s, 0.05 if s else 0.0) + extra


# ---------------------------------------------------------------- recorrido

def hijos_de(nodo):
    cont = nodo.find(Q("EstructurasFuncionales"))
    return list(cont.findall(Q("EstructuraFuncional"))) if cont is not None else []


def sin_tildes(s):
    tabla = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return s.translate(tabla).lower()


def articulados_de(raiz):
    """Los textos refundidos que fija una norma, con el artículo que los fija.

    Un DFL puede fijar varios de una vez. El idNorma 172986 no es «el Código
    Civil»: es el DFL 1 de 2000, que fija en un mismo cuerpo el Código Civil,
    la Ley sobre Registro Civil, la Ley de Menores y tres leyes más. Cada uno
    numera sus artículos desde el 1, así que publicarlos juntos produciría
    seis artículos «1», seis «2», y un texto que no es ningún código.
    """
    padres = {h: p for p in raiz.iter() for h in p}
    fuera = []
    for ef in raiz.iter(Q("EstructuraFuncional")):
        if (ef.get("tipoParte") or "").strip().lower() != "doble articulado":
            continue
        p = padres.get(ef)
        while p is not None and p.tag != Q("EstructuraFuncional"):
            p = padres.get(p)
        propios = incisos_de(p) if p is not None else []
        fuera.append((ef, propios[0].strip() if propios else "(sin encabezado)"))
    return fuera


def elegir_articulado(raiz, pedido):
    """Devuelve los nodos de primer nivel del cuerpo legal que corresponde.

    Sin «Doble Articulado» la norma es lo que dice ser y se devuelve entera.
    Con uno solo, se entra en él: la norma es el decreto que fija el texto, y
    el texto es lo que está adentro. Con varios hay que decir cuál, porque
    adivinar sería publicar un código con el contenido de otro.
    """
    cont = raiz.find(Q("EstructurasFuncionales"))
    todo = list(cont.findall(Q("EstructuraFuncional"))) if cont is not None else []

    dobles = articulados_de(raiz)
    if not dobles:
        if pedido:
            raise SystemExit("esta norma no fija textos refundidos: sobra --articulado")
        return todo, ""

    if pedido:
        elegidos = [(n, t) for n, t in dobles if sin_tildes(pedido) in sin_tildes(t)]
        if len(elegidos) != 1:
            cuales = "\n".join(f"  · {t}" for _, t in dobles)
            raise SystemExit(
                f"«{pedido}» calza con {len(elegidos)} de los {len(dobles)} textos "
                f"que fija esta norma. Los que hay:\n{cuales}")
        nodo, encabezado = elegidos[0]
    elif len(dobles) == 1:
        nodo, encabezado = dobles[0]
    else:
        cuales = "\n".join(f"  · {t}" for _, t in dobles)
        raise SystemExit(
            f"esta norma fija {len(dobles)} textos refundidos distintos. Hay que "
            f"elegir uno con --articulado; si no, saldrían mezclados:\n{cuales}")

    return hijos_de(nodo), encabezado


def es_indice(ef, tipo):
    """¿Este nodo merece una entrada en el índice lateral?

    Sí cuando la BCN le puso un título propio, o cuando su tipo es uno de los
    que arman un código. El resto son envoltorios sin nombre: el Código Civil
    cuelga sus cuatro Libros dentro de nodos de tipo «Artículo», y el
    Tributario mete el código entero dentro de uno solo. Si esos envoltorios
    entraran al índice, aparecerían como renglones vacíos; si no se
    atravesaran, el índice quedaría vacío del todo.
    """
    return bool(titulo_de(ef)) or tipo.lower() in TIPOS_ESTRUCTURA


def recorrer(nodos, articulos, ruta, transitorio=False):
    """Recorre el árbol de la norma juntando artículos y armando el índice.

    `transitorio` se hereda hacia abajo: la BCN marca los nodos con un atributo
    propio, y los artículos transitorios vuelven a numerar desde 1. Sin
    distinguirlos, el Código Tributario tendría dos artículos «1» y el enlace a
    uno llevaría al otro.
    """
    ramas = []
    for ef in nodos:
        tipo = (ef.get("tipoParte") or "Sección").strip()
        derogado = (ef.get("derogado") or "").lower().startswith("derog")
        es_trans = transitorio or (ef.get("transitorio") or "").strip().lower() == "transitorio"

        if tipo.lower().startswith("art"):
            propios = incisos_de(ef)
            num, epi, cuerpo = partir_articulo(propios)
            if num:
                # Si el nodo solo trae el encabezado («ART. 2.») el texto vive
                # en los nodos hijos: se recoge de ahí antes de seguir.
                if not cuerpo:
                    for hijo in hijos_de(ef):
                        cuerpo += incisos_de(hijo)
                # «1» del articulado transitorio no es el «1» del permanente.
                if es_trans and num.lower() not in ("transitorio", "final", "único"):
                    num = f"{num} transitorio"
                desde = ef.get("fechaVersion") or ""
                articulos.append({
                    "n": num, "ord": orden(num), "epi": epi, "p": cuerpo,
                    "derogado": derogado,
                    "desde": desde if fecha_plausible(desde) else "",
                    "ruta": list(ruta),
                })
            # Bajar igual, y quedarse con lo que traiga: hay códigos que anidan
            # artículos —y códigos enteros— dentro de nodos de tipo «Artículo».
            ramas.extend(recorrer(hijos_de(ef), articulos, ruta, es_trans))
            continue

        if not es_indice(ef, tipo):
            # Envoltorio sin nombre: se atraviesa y lo que haya adentro sube.
            ramas.extend(recorrer(hijos_de(ef), articulos, ruta, es_trans))
            continue

        titulo = titulo_de(ef) or " ".join(incisos_de(ef)[:2])
        numero, nombre = partir_cabecera(titulo, tipo)
        rama = {"tipo": tipo, "num": numero, "nombre": nombre or titulo,
                "hijos": [], "arts": [], "derogado": derogado}
        antes = len(articulos)
        rama["hijos"] = recorrer(hijos_de(ef), articulos,
                                 ruta + [f"{tipo} {numero}".strip()], es_trans)
        rama["arts"] = [a["n"] for a in articulos[antes:]] if not rama["hijos"] else []
        ramas.append(rama)
    return ramas


# ---------------------------------------------------------------- principal

def main():
    ap = argparse.ArgumentParser(description="Ingesta de normas desde Ley Chile (BCN)")
    ap.add_argument("id_norma")
    ap.add_argument("-o", "--salida", default="norma.json")
    ap.add_argument("--fecha", help="fechaVersion AAAA-MM-DD")
    ap.add_argument("--xml", help="ruta a un XML ya descargado")
    ap.add_argument("--js", help="además del JSON, escribe el archivo que carga el lector "
                                 "(window.NORMA=...), que es como el sitio consume los datos")
    ap.add_argument("--articulado",
                    help='cuando la norma fija varios textos refundidos, cuál se '
                         'quiere (p. ej. "Código Civil")')
    args = ap.parse_args()

    crudo = open(args.xml, "rb").read() if args.xml else descargar(args.id_norma, args.fecha)
    crudo = sanear(crudo)
    raiz = ET.fromstring(crudo)

    ident = raiz.find(Q("Identificador"))
    meta = raiz.find(Q("Metadatos"))

    def texto(nodo, *ruta):
        for r in ruta:
            if nodo is None:
                return ""
            nodo = nodo.find(Q(r))
        return re.sub(r"\s+", " ", (nodo.text or "")).strip() if nodo is not None else ""

    articulos = []
    nodos, fijado_por = elegir_articulado(raiz, args.articulado)
    if fijado_por:
        print(f"    texto refundido tomado de: {fijado_por[:90]}", file=sys.stderr)
    arbol = recorrer(nodos, articulos, [])

    # La fecha de la versión. Si la raíz trae el centinela 2222-02-02, se usa
    # la modificación más reciente que el propio archivo declara: es la fecha
    # hasta la cual el texto está efectivamente al día, y es verificable.
    publicacion = (ident.get("fechaPublicacion") if ident is not None else "") or ""
    ultima = raiz.get("fechaVersion") or args.fecha or ""
    inferida = False
    if not fecha_plausible(ultima):
        candidatas = sorted(f for f in
                            {e.get("fechaVersion") for e in raiz.iter(Q("EstructuraFuncional"))}
                            if fecha_plausible(f))
        origen = ultima or "(vacía)"
        ultima = candidatas[-1] if candidatas else publicacion
        inferida = True
        print(f"    la BCN declara fechaVersion={origen}; uso {ultima}, "
              f"la modificación más reciente del archivo", file=sys.stderr)

    tipo = texto(ident, "TiposNumeros", "TipoNumero", "Tipo")
    numero = texto(ident, "TiposNumeros", "TipoNumero", "Numero")
    if numero.isdigit() and len(numero) > 3:
        numero = f"{int(numero):,}".replace(",", ".")

    salida = {
        "idNorma": args.id_norma,
        "titulo": texto(meta, "TituloNorma"),
        "ley": f"{tipo} {numero}".strip(),
        "organismo": texto(ident, "Organismos", "Organismo"),
        "promulgacion": (ident.get("fechaPromulgacion") if ident is not None else "") or "",
        "publicacion": publicacion,
        "ultimaVersion": ultima,
        "versionInferida": inferida,
        "fuente": f"https://www.bcn.cl/leychile/navegar?idNorma={args.id_norma}",
        "estructura": arbol,
        "articulos": sorted(articulos, key=lambda a: a["ord"]),
    }

    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)

    if args.js:
        # El lector carga los datos con <script src>, no con fetch: así funciona
        # también al abrir el archivo con doble clic, sin servidor.
        with open(args.js, "w", encoding="utf-8") as f:
            f.write("window.NORMA=")
            json.dump(salida, f, ensure_ascii=False, separators=(",", ":"))
            f.write(";")

    sin_epi = sum(1 for a in articulos if not a["epi"])
    print(f"{len(articulos)} artículos → {args.salida} "
          f"({sin_epi} sin epígrafe, {sum(1 for a in articulos if a['derogado'])} derogados)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
