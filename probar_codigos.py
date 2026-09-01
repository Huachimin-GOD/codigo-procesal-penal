#!/usr/bin/env python3
"""Prueba en seco: corre la ingesta sobre varios códigos y reporta, sin publicar.

Sirve para ver cuáles parsean limpio antes de decidir qué se publica.
Se ejecuta en GitHub Actions, que sí tiene acceso a la BCN.
"""
import sys, time
import ingesta_bcn as ing

# Los quince códigos de la República, tal como los lista la BCN en
# https://www.bcn.cl/leychile/codigos (identificadores leídos de esa página).
CODIGOS = [
    ("Civil",                          172986),
    ("Penal",                            1984),
    ("del Trabajo",                    207436),
    ("de Comercio",                      1974),
    ("Tributario",                       6374),
    ("de Procedimiento Civil",          22740),
    ("Procesal Penal",                 176595),
    ("Orgánico de Tribunales",          25563),
    ("de Aguas",                         5605),
    ("de Minería",                      29668),
    ("Aeronáutico",                     30287),
    ("Sanitario",                        5595),
    ("de Justicia Militar",             18914),
    ("de Derecho Internacional Privado", 12820),
    ("de Procedimiento Penal (antiguo)", 22960),
]


def analizar(id_norma):
    crudo = ing.sanear(ing.descargar(str(id_norma)))
    import xml.etree.ElementTree as ET
    raiz = ET.fromstring(crudo)
    arts = []
    cont = raiz.find(ing.Q("EstructurasFuncionales"))
    arbol = ing.recorrer(list(cont.findall(ing.Q("EstructuraFuncional"))), arts, []) if cont is not None else []

    ident = raiz.find(ing.Q("Identificador"))
    def prof(rama, d=1):
        return max([prof(h, d + 1) for h in rama["hijos"]] or [d])

    return {
        "articulos": len(arts),
        "sin_epigrafe": sum(1 for a in arts if not a["epi"]),
        "derogados": sum(1 for a in arts if a["derogado"]),
        "sin_texto": sum(1 for a in arts if not a["p"]),
        "ramas": len(arbol),
        "profundidad": max([prof(r) for r in arbol] or [0]),
        "version": raiz.get("fechaVersion") or "?",
        "publicacion": (ident.get("fechaPublicacion") if ident is not None else "?"),
        "peso_kb": round(len(crudo) / 1024),
    }


# La BCN limita las peticiones seguidas. Con 20 segundos entre códigos la
# prueba completa toma unos cinco minutos y no la molestamos.
PAUSA = 20


def main():
    filas, fallos = [], []
    for i, (nombre, id_norma) in enumerate(CODIGOS):
        if i:
            time.sleep(PAUSA)
        try:
            r = analizar(id_norma)
            filas.append((nombre, id_norma, r))
            print(f"  ok   {nombre:36} {r['articulos']:>5} artículos", file=sys.stderr, flush=True)
        except Exception as e:
            fallos.append((nombre, id_norma, f"{type(e).__name__}: {e}"))
            print(f"  FALLA {nombre:36} {e}", file=sys.stderr, flush=True)

    print()
    print("| Código | idNorma | Artículos | Sin epígrafe | Derogados | Sin texto | Niveles | Versión | XML |")
    print("|---|---:|---:|---:|---:|---:|---:|---|---:|")
    for nombre, id_norma, r in sorted(filas, key=lambda f: -f[2]["articulos"]):
        alerta = "" if r["articulos"] > 20 and r["sin_texto"] == 0 else "  ⚠"
        print(f"| Código {nombre}{alerta} | {id_norma} | {r['articulos']} | {r['sin_epigrafe']} | "
              f"{r['derogados']} | {r['sin_texto']} | {r['profundidad']} | {r['version']} | {r['peso_kb']} KB |")

    total = sum(r["articulos"] for _, _, r in filas)
    print(f"\n**{len(filas)} códigos · {total:,} artículos en total**".replace(",", "."))

    if fallos:
        print("\n### No se pudieron procesar\n")
        for nombre, id_norma, err in fallos:
            print(f"- Código {nombre} ({id_norma}): {err}")


if __name__ == "__main__":
    main()
