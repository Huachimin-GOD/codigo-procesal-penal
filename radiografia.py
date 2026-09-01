#!/usr/bin/env python3
"""Radiografía de una norma: por qué el parser encuentra menos de lo que hay.

No vuelca el XML (pesa megas). Cuenta nodos, muestra qué tipos de parte
existen y, sobre todo, cuántos artículos rechaza la expresión regular y
cómo empiezan los que rechaza. Se ejecuta en GitHub Actions.
"""
import collections, sys
import xml.etree.ElementTree as ET
import ingesta_bcn as ing

NORMAS = [
    ("Civil", 172986),
    ("Penal", 1984),
    ("Tributario", 6374),
    ("Procesal Penal (control)", 176595),
]


def radiografiar(nombre, id_norma):
    crudo = ing.sanear(ing.descargar(str(id_norma)))
    raiz = ET.fromstring(crudo)

    tipos = collections.Counter()
    nodos_art, aceptados, rechazados = [], 0, []

    for ef in raiz.iter(ing.Q("EstructuraFuncional")):
        t = (ef.get("tipoParte") or "(sin tipo)").strip()
        tipos[t] += 1
        if t.lower().startswith("art"):
            nodos_art.append(ef)

    for ef in nodos_art:
        incisos = ing.incisos_de(ef)
        num, _, _ = ing.partir_articulo(incisos)
        if num:
            aceptados += 1
        elif len(rechazados) < 6:
            primera = (incisos[0] if incisos else "(sin texto)")[:90]
            rechazados.append(primera)

    # ¿cuántos artículos alcanza el recorrido, comparado con cuántos hay?
    arts = []
    cont = raiz.find(ing.Q("EstructurasFuncionales"))
    if cont is not None:
        ing.recorrer(list(cont.findall(ing.Q("EstructuraFuncional"))), arts, [])

    print(f"\n### {nombre}  (idNorma {id_norma})\n")
    print(f"- XML: **{len(crudo)/1024:,.0f} KB**")
    print(f"- Nodos con tipoParte «Artículo» en todo el archivo: **{len(nodos_art)}**")
    print(f"- De esos, la expresión regular reconoce: **{aceptados}**")
    print(f"- Los que devuelve el recorrido actual: **{len(arts)}**")
    print(f"- Tipos de parte presentes: " +
          ", ".join(f"`{t}`×{n}" for t, n in tipos.most_common(12)))
    if rechazados:
        print("\nAsí empiezan los artículos que la expresión regular rechaza:\n")
        for r in rechazados:
            print(f"    {r}")
    print()


def main():
    for i, (nombre, id_norma) in enumerate(NORMAS):
        if i:
            import time; time.sleep(20)
        try:
            radiografiar(nombre, id_norma)
        except Exception as e:
            print(f"\n### {nombre}: FALLA — {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    main()
