#!/usr/bin/env python3
"""Prueba en seco: corre la ingesta sobre varios códigos y reporta, sin publicar.

Sirve para ver cuáles parsean limpio antes de decidir qué se publica.
Se ejecuta en GitHub Actions, que sí tiene acceso a la BCN.
"""
import sys, time
import ingesta_bcn as ing

# Los quince códigos de la República, tal como los lista la BCN en
# https://www.bcn.cl/leychile/codigos (identificadores leídos de esa página).
# Algunas normas fijan varios textos refundidos de una vez: el 172986 no es
# «el Código Civil», es el DFL 1 de 2000, que fija el Código Civil y otros
# cinco cuerpos legales. El tercer campo dice cuál de ellos queremos.
CODIGOS = [
    ("Civil",                          172986, "Código Civil"),
    ("Penal",                            1984, None),
    ("del Trabajo",                    207436, None),
    ("de Comercio",                      1974, None),
    ("Tributario",                       6374, None),
    ("de Procedimiento Civil",          22740, None),
    ("Procesal Penal",                 176595, None),
    ("Orgánico de Tribunales",          25563, None),
    ("de Aguas",                         5605, None),
    ("de Minería",                      29668, None),
    ("Aeronáutico",                     30287, None),
    ("Sanitario",                        5595, None),
    ("de Justicia Militar",             18914, None),
    ("de Derecho Internacional Privado", 12820, None),
    ("de Procedimiento Penal (antiguo)", 22960, None),
]


def analizar(id_norma, articulado):
    crudo = ing.sanear(ing.descargar(str(id_norma)))
    import xml.etree.ElementTree as ET
    raiz = ET.fromstring(crudo)
    arts = []
    nodos, fijado_por = ing.elegir_articulado(raiz, articulado)
    arbol = ing.recorrer(nodos, arts, [])

    ident = raiz.find(ing.Q("Identificador"))
    # La fecha, con la misma corrección que aplica la ingesta.
    cruda = raiz.get("fechaVersion") or ""
    inferida = not ing.fecha_plausible(cruda)
    if inferida:
        buenas = sorted(f for f in {e.get("fechaVersion")
                                    for e in raiz.iter(ing.Q("EstructuraFuncional"))}
                        if ing.fecha_plausible(f))
        version = buenas[-1] if buenas else "?"
    else:
        version = cruda
    def prof(rama, d=1):
        return max([prof(h, d + 1) for h in rama["hijos"]] or [d])

    return {
        "articulos": len(arts),
        "sin_epigrafe": sum(1 for a in arts if not a["epi"]),
        "derogados": sum(1 for a in arts if a["derogado"]),
        "sin_texto": sum(1 for a in arts if not a["p"]),
        "ramas": len(arbol),
        "profundidad": max([prof(r) for r in arbol] or [0]),
        "version": version,
        "inferida": inferida,
        "cruda": cruda,
        "fijado_por": fijado_por,
        "publicacion": (ident.get("fechaPublicacion") if ident is not None else "?"),
        "peso_kb": round(len(crudo) / 1024),
    }


# La BCN limita las peticiones seguidas. Con 20 segundos entre códigos la
# prueba completa toma unos cinco minutos y no la molestamos.
PAUSA = 20


def main():
    filas, fallos = [], []
    for i, (nombre, id_norma, articulado) in enumerate(CODIGOS):
        if i:
            time.sleep(PAUSA)
        try:
            r = analizar(id_norma, articulado)
            filas.append((nombre, id_norma, r))
            print(f"  ok   {nombre:36} {r['articulos']:>5} artículos", file=sys.stderr, flush=True)
        except Exception as e:
            fallos.append((nombre, id_norma, f"{type(e).__name__}: {e}"))
            print(f"  FALLA {nombre:36} {e}", file=sys.stderr, flush=True)

    print()
    print("| Código | idNorma | Artículos | Sin epígrafe | Derogados | Sin texto | Niveles | Versión | XML |")
    print("|---|---:|---:|---:|---:|---:|---:|---|---:|")
    for nombre, id_norma, r in sorted(filas, key=lambda f: -f[2]["articulos"]):
        # Ahora un código sin niveles también es una alerta: su índice saldría vacío.
        malo = r["articulos"] <= 20 or r["sin_texto"] or r["profundidad"] == 0
        fecha = r["version"] + (" ¹" if r["inferida"] else "")
        print(f"| Código {nombre}{'  ⚠' if malo else ''} | {id_norma} | {r['articulos']} | "
              f"{r['sin_epigrafe']} | {r['derogados']} | {r['sin_texto']} | "
              f"{r['profundidad']} | {fecha} | {r['peso_kb']} KB |")

    inferidas = [(n, r) for n, _, r in filas if r["inferida"]]
    if inferidas:
        print("\n¹ La BCN no declara una fecha usable en la raíz; se usa la modificación "
              "más reciente que trae el propio archivo:\n")
        for n, r in inferidas:
            print(f"- Código {n}: la raíz dice `{r['cruda'] or '(vacía)'}` → se usa **{r['version']}**")

    refundidos = [(n, r) for n, _, r in filas if r["fijado_por"]]
    if refundidos:
        print("\nTextos refundidos: la norma es el decreto y el código va dentro.\n")
        for n, r in refundidos:
            print(f"- Código {n}: {r['fijado_por'][:110]}")

    total = sum(r["articulos"] for _, _, r in filas)
    print(f"\n**{len(filas)} códigos · {total:,} artículos en total**".replace(",", "."))

    if fallos:
        print("\n### No se pudieron procesar\n")
        for nombre, id_norma, err in fallos:
            print(f"- Código {nombre} ({id_norma}): {err}")


if __name__ == "__main__":
    main()
