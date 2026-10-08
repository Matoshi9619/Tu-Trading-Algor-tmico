"""
MOTOR DE LA APP "Nuestra Inversión"
===================================
Se ejecuta solo en GitHub cada día hábil después del cierre de la bolsa de Nueva York.
  1. Descarga precios reales (SPY, EFA, IEF, SHY y el dólar en soles).
  2. Calcula el "semáforo" del mercado.
  3. Hace jugar a los 6 robots con dinero ficticio (simulación hacia adelante).
  4. Calcula la historia de 20 años, las crisis y los datos de la calculadora.
  5. Guarda todo en docs/data.json, que es lo que lee la app.

Prueba local sin internet:  python motor/actualizar.py --demo --fecha 2026-03-02
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import estrategias as es  # noqa: E402

RAIZ = os.path.dirname(AQUI)
DATA = os.path.join(RAIZ, "docs", "data.json")
ESTADO = os.path.join(AQUI, "estado_robots.json")

CAPITAL = 10000.0
COSTO = 0.001
TOLERANCIA = 0.05
DIVISION = "2018-01-01"

ROBOTS = [  # id, nombre sencillo, explicación corta, explicación larga
    ("0. Comprar y mantener SPY", "Sin hacer nada",
     "Compra el fondo de las 500 empresas más grandes de EE. UU. y lo guarda para siempre.",
     "Es la referencia. No toma decisiones: compra y espera. Si un robot no le gana a este, no vale la pena."),
    ("1. Cartera 60/40", "Mitad segura",
     "Siempre 60% en acciones y 40% en bonos.",
     "Los bonos amortiguan las caídas. Gana menos que las acciones solas, pero sufre menos en las crisis."),
    ("2. Cruce de medias 50/200", "Sigue la tendencia",
     "Compra acciones cuando el mercado viene subiendo; si empieza a bajar, se sale a efectivo.",
     "Compara el precio promedio de los últimos 3 meses con el del último año. Reacciona lento: sirve en caídas largas, no en las rápidas."),
    ("3. Filtro de tendencia", "Revisión mensual",
     "Una vez al mes: acciones si van subiendo, bonos si van bajando.",
     "El último día de cada mes mira si las acciones están por encima de su promedio del último año. Si no, se refugia en bonos."),
    ("4. Rotación por momentum", "Apuesta al que gana",
     "Cada mes elige entre acciones de EE. UU., del resto del mundo o bonos.",
     "Invierte en lo que más subió en los últimos 12 meses. Si nada le gana a guardar el dinero, se va a bonos."),
    ("5. Rebote de corto plazo RSI", "Compra en las caídas",
     "Compra después de caídas fuertes de pocos días y vende cuando rebota.",
     "Solo entra cuando el mercado cae de golpe dentro de una subida. Pasa casi todo el tiempo en efectivo."),
]
ACTIVOS = {"SPY": "Acciones de EE. UU.", "EFA": "Acciones del resto del mundo",
           "IEF": "Bonos del gobierno de EE. UU.", "SHY": "Bonos de corto plazo"}
CRISIS = [("Crisis financiera de 2008", "2007-10-09", "2009-03-09"),
          ("Pandemia COVID-19 (2020)", "2020-02-19", "2020-03-23"),
          ("Inflación y subida de tasas (2022)", "2022-01-03", "2022-10-12")]


# ============================================================ datos
def descargar(args):
    if args.demo:
        class A: demo = True
        p = es.cargar_precios(A)
        if args.fecha:
            p = p.loc[: args.fecha]
        tc = pd.Series(3.40 + 0.3 * np.sin(np.arange(len(p)) / 900), index=p.index, name="PEN")
        return p, tc
    import yfinance as yf
    df = yf.download(es.ACTIVOS + ["PEN=X"], start="2002-08-01", auto_adjust=True, progress=False)["Close"]
    tc = df["PEN=X"].ffill()
    p = df[es.ACTIVOS].dropna()
    if len(p) < 1000:
        sys.exit("No se pudieron descargar los precios.")
    return p, tc.reindex(p.index).ffill().bfill()


def r(x, n=4):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), n)


# ============================================================ 1. semáforo del mercado
def mercado(p: pd.DataFrame, tc: pd.Series) -> dict:
    def cambio(s, dias):
        return s.iloc[-1] / s.iloc[-1 - dias] - 1 if len(s) > dias else None

    activos = []
    for t in es.ACTIVOS:
        s = p[t]
        maximo = s.iloc[-252:].max()
        activos.append({
            "ticker": t, "nombre": ACTIVOS[t], "precio": r(s.iloc[-1], 2),
            "dia": r(cambio(s, 1)), "semana": r(cambio(s, 5)), "mes": r(cambio(s, 21)),
            "anio": r(cambio(s, 252)), "sobre_promedio": bool(s.iloc[-1] > s.iloc[-200:].mean()),
            "desde_maximo": r(s.iloc[-1] / maximo - 1),
            "serie": [[d.strftime("%Y-%m-%d"), r(v, 2)] for d, v in s.iloc[-252:].items()],
        })
    spy = p["SPY"]
    prom200 = spy.iloc[-200:].mean()
    sobre = spy.iloc[-1] > prom200
    caida = spy.iloc[-1] / spy.iloc[-252:].max() - 1
    mes = cambio(spy, 21)
    vol = spy.pct_change().iloc[-21:].std() * np.sqrt(252)

    if sobre and caida > -0.05:
        color, titular = "verde", "El mercado está en subida"
        texto = ("Las acciones de EE. UU. están por encima de su precio promedio del último año "
                 f"y apenas a {abs(caida):.0%} de su punto más alto. Es un momento tranquilo.")
    elif sobre or caida > -0.10:
        color, titular = "amarillo", "El mercado está dudando"
        texto = (f"Las acciones de EE. UU. están {abs(caida):.0%} por debajo de su punto más alto del último año. "
                 + ("Siguen por encima de su promedio anual, así que la tendencia de fondo aún es de subida."
                    if sobre else "Están por debajo de su promedio anual: hay que estar atentos."))
    else:
        color, titular = "rojo", "El mercado está en caída"
        texto = (f"Las acciones de EE. UU. han caído {abs(caida):.0%} desde su punto más alto del último año "
                 "y están por debajo de su promedio anual. En momentos así algunos robots se refugian en bonos.")
    if vol > 0.25:
        texto += " Además, los precios se están moviendo mucho de un día a otro (más nervios de lo normal)."

    return {
        "color": color, "titular": titular, "explicacion": texto,
        "spy_mes": r(mes), "spy_desde_maximo": r(caida), "spy_sobre_promedio": bool(sobre),
        "volatilidad": r(vol), "tipo_cambio": r(tc.iloc[-1], 3), "activos": activos,
    }


# ============================================================ 2. competencia de robots
def pesos_actuales(c, hoy):
    total = valor(c, hoy)
    return {t: c["pos"].get(t, 0) * hoy[t] / total for t in es.ACTIVOS}


def valor(c, hoy):
    return c["efectivo"] + sum(a * hoy[t] for t, a in c["pos"].items())


def necesita_cambio(act, obj):
    return any(((act.get(t, 0) > 0.001) != (obj.get(t, 0) > 0.001)) or abs(act.get(t, 0) - obj.get(t, 0)) > TOLERANCIA
               for t in es.ACTIVOS)


def reequilibrar(nombre, c, obj, hoy, fecha):
    ops, total = [], valor(c, hoy)
    for t in es.ACTIVOS:                                  # ventas
        tiene, quiere = c["pos"].get(t, 0), obj.get(t, 0) * total / hoy[t]
        if tiene - quiere > 1e-9:
            monto = (tiene - quiere) * hoy[t]
            c["efectivo"] += monto * (1 - COSTO)
            c["pos"][t] = quiere
            ops.append({"fecha": fecha, "robot": nombre, "activo": t, "accion": "vendió", "monto": round(monto, 2)})
    for t in es.ACTIVOS:                                  # compras
        tiene, quiere = c["pos"].get(t, 0), obj.get(t, 0) * total / hoy[t]
        if quiere - tiene > 1e-9:
            monto = min((quiere - tiene) * hoy[t], c["efectivo"] / (1 + COSTO))
            if monto < 1:
                continue
            c["efectivo"] -= monto * (1 + COSTO)
            c["pos"][t] = tiene + monto / hoy[t]
            ops.append({"fecha": fecha, "robot": nombre, "activo": t, "accion": "compró", "monto": round(monto, 2)})
    c["pos"] = {t: a for t, a in c["pos"].items() if a > 1e-9}
    c["efectivo"] = max(c["efectivo"], 0.0)
    return ops


def robots(p: pd.DataFrame) -> dict:
    fecha = p.index[-1].strftime("%Y-%m-%d")
    hoy = p.iloc[-1]
    if os.path.exists(ESTADO):
        est = json.load(open(ESTADO, encoding="utf-8"))
    else:
        est = {"inicio": fecha, "ultima": None, "historial": [], "operaciones": [],
               "carteras": {rid: {"efectivo": CAPITAL, "pos": {}} for rid, *_ in ROBOTS}}
    if est["ultima"] != fecha:
        fila = {"fecha": fecha}
        for rid, *_ in ROBOTS:
            obj = es.ESTRATEGIAS[rid](p).iloc[-1].to_dict()
            c = est["carteras"][rid]
            if necesita_cambio(pesos_actuales(c, hoy), obj):
                est["operaciones"] += reequilibrar(rid, c, obj, hoy, fecha)
            fila[rid] = round(valor(c, hoy), 2)
        est["historial"].append(fila)
        est["ultima"] = fecha
        json.dump(est, open(ESTADO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    salida = []
    for rid, nombre, corta, larga in ROBOTS:
        c = est["carteras"][rid]
        salida.append({
            "id": rid[0], "nombre": nombre, "corta": corta, "larga": larga,
            "valor": round(valor(c, hoy), 2),
            "pesos": {t: r(w) for t, w in pesos_actuales(c, hoy).items() if w > 0.001},
            "serie": [[h["fecha"], h[rid]] for h in est["historial"]],
        })
    ops = [dict(o, robot=next(n for i, n, *_ in ROBOTS if i == o["robot"])) for o in est["operaciones"][-40:]]
    return {"inicio": est["inicio"], "dias": len(est["historial"]), "capital": CAPITAL,
            "robots": salida, "operaciones": list(reversed(ops))}


# ============================================================ 3. historia de 20 años
def historia(p: pd.DataFrame) -> dict:
    inicio = p.index[260]
    d = pd.Timestamp(DIVISION)
    curvas, metricas, crisis = {}, [], []
    for rid, nombre, *_ in ROBOTS:
        ret, pos, rot = es.simular(es.ESTRATEGIAS[rid](p), p, COSTO)
        ret = ret.loc[inicio:]
        curva = (1 + ret).cumprod()
        curvas[rid[0]] = curva
        fila = {"id": rid[0], "nombre": nombre}
        for clave, desde, hasta in (("todo", inicio, None), ("antes", inicio, d - pd.Timedelta(days=1)), ("prueba", d, None)):
            m = es.metricas(ret.loc[desde:hasta], pos.loc[desde:hasta], rot.loc[desde:hasta])
            fila[clave] = {"anual": r(m["Rent. anual"]), "caida": r(m["Peor caída"]),
                           "final": round(m["S/10k ->"]), "invertido": r(m["% invertido"])}
        metricas.append(fila)
    for titulo, a, b in CRISIS:
        if pd.Timestamp(a) < inicio or pd.Timestamp(b) > p.index[-1]:
            continue
        fila = {"titulo": titulo, "desde": a, "hasta": b, "robots": []}
        for rid, nombre, *_ in ROBOTS:
            c = curvas[rid[0]]
            tramo = c.loc[a:b]
            fila["robots"].append({"id": rid[0], "nombre": nombre, "cambio": r(tramo.iloc[-1] / tramo.iloc[0] - 1)})
        crisis.append(fila)
    # curvas mensuales (para gráfico y calculadora)
    mens = pd.DataFrame(curvas).resample("ME").last()
    return {
        "desde": inicio.strftime("%Y-%m-%d"), "division": DIVISION, "metricas": metricas, "crisis": crisis,
        "meses": [i.strftime("%Y-%m") for i in mens.index],
        "curvas": {k: [r(v, 5) for v in mens[k]] for k in mens.columns},
    }


# ============================================================ principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--fecha")
    args = ap.parse_args()
    p, tc = descargar(args)
    data = {
        "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "fecha_precios": p.index[-1].strftime("%Y-%m-%d"),
        "demo": bool(args.demo),
        "mercado": mercado(p, tc),
        "robots": robots(p),
        "historia": historia(p),
    }
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"OK: datos del {data['fecha_precios']} -> {DATA} ({os.path.getsize(DATA) / 1024:.0f} KB)")
    print(f"Mercado: {data['mercado']['titular']} | Robots: {data['robots']['dias']} días")


if __name__ == "__main__":
    main()
