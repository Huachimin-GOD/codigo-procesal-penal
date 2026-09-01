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
        "User-Agent": "ingesta-leyes/2.0 (+https://github.com/Huachimin-GOD/codigo-procesal-penal)",
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
RX_ART = re.compile(
    r"^\s*(?:art[íi]culos?|arts?)\.?\s*"
    r"(\d+[º°]?"
    r"(?:\s*(?:bis|ter|qu[aá]ter|quinquies|sexies|septies|octies|nonies|decies))?"
    r"(?:\s+[A-Z](?=\s*[.\-–]))?)"
    r"\s*[.\-–]*\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)

# «Artículo transitorio.-» y «Artículo final»: sin número, pero son artículos.
RX_ART_SIN_NUMERO = re.compile(
    r"^\s*(?:art[íi]culos?|arts?)\.?\s+(transitorio|final|[úu]nico)\b\s*[.\-–]*\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)


def normaliza_num(n):
    n = re.sub(r"\s+", " ", n.replace("º", "").replace("°", "")).strip()
    return n


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
    # Los transitorios y finales van al final, después del articulado permanente.
    if num.lower() in ("transitorio", "final", "único"):
        return 1e6 + {"transitorio": 1, "único": 2, "final": 3}[num.lower()]
    m = re.match(r"^(\d+)(?:\s*(bis|ter|qu[aá]ter|quinquies|sexies|septies|octies|nonies|decies))?"
                 r"(?:\s*([A-Z]))?$", num, re.IGNORECASE)
    if not m:
        return 0.0
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


def recorrer(nodos, articulos, ruta):
    ramas = []
    for ef in nodos:
        tipo = (ef.get("tipoParte") or "Sección").strip()
        derogado = (ef.get("derogado") or "").lower().startswith("derog")

        if tipo.lower().startswith("art"):
            propios = incisos_de(ef)
            num, epi, cuerpo = partir_articulo(propios)
            if num:
                # Si el nodo solo trae el encabezado («ART. 2.») el texto vive
                # en los nodos hijos: se recoge de ahí antes de seguir.
                if not cuerpo:
                    for hijo in hijos_de(ef):
                        cuerpo += incisos_de(hijo)
                articulos.append({
                    "n": num, "ord": orden(num), "epi": epi, "p": cuerpo,
                    "derogado": derogado, "desde": ef.get("fechaVersion") or "",
                    "ruta": list(ruta),
                })
            # Bajar igual: hay códigos que anidan artículos dentro de otros
            # nodos de tipo «Artículo» o dentro de «Doble Articulado».
            recorrer(hijos_de(ef), articulos, ruta)
            continue

        titulo = titulo_de(ef) or " ".join(incisos_de(ef)[:2])
        numero, nombre = partir_cabecera(titulo, tipo)
        rama = {"tipo": tipo, "num": numero, "nombre": nombre or titulo,
                "hijos": [], "arts": [], "derogado": derogado}
        antes = len(articulos)
        rama["hijos"] = recorrer(hijos_de(ef), articulos, ruta + [f"{tipo} {numero}".strip()])
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
    cont = raiz.find(Q("EstructurasFuncionales"))
    arbol = recorrer(list(cont.findall(Q("EstructuraFuncional"))) if cont is not None else [],
                     articulos, [])

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
        "publicacion": (ident.get("fechaPublicacion") if ident is not None else "") or "",
        "ultimaVersion": raiz.get("fechaVersion") or args.fecha or "",
        "fuente": f"https://www.bcn.cl/leychile/navegar?idNorma={args.id_norma}",
        "estructura": arbol,
        "articulos": sorted(articulos, key=lambda a: a["ord"]),
    }

    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)

    sin_epi = sum(1 for a in articulos if not a["epi"])
    print(f"{len(articulos)} artículos → {args.salida} "
          f"({sin_epi} sin epígrafe, {sum(1 for a in articulos if a['derogado'])} derogados)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
