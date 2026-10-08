"""
COMPARADOR DE ESTRATEGIAS — Trading algorítmico
================================================
Prueba varias estrategias con las mismas reglas de juego y las compara lado a lado.

Activos usados (fondos ETF que cotizan en EE. UU.):
  SPY = acciones de EE. UU. (las 500 empresas más grandes, índice S&P 500)
  EFA = acciones internacionales (Europa, Japón, Australia...)
  IEF = bonos del gobierno de EE. UU. a 7-10 años (suelen subir o aguantar cuando las acciones caen)
  SHY = bonos del gobierno de EE. UU. a 1-3 años (casi como tener efectivo que rinde intereses)

Estrategias:
  0. Comprar y mantener SPY     -> la referencia: no hacer nada
  1. Cartera 60/40              -> 60% SPY + 40% IEF, se reequilibra cada mes (no es "algoritmo", es la cartera clásica)
  2. Cruce de medias 50/200     -> comprado en SPY si la media de 50 días > la de 200; si no, en efectivo
  3. Filtro de tendencia        -> fin de mes: si SPY > su media de 200 días, en SPY; si no, en bonos IEF
  4. Rotación por momentum      -> fin de mes: elige entre SPY y EFA el que más subió en 12 meses;
                                   si ninguno le gana a SHY (efectivo), se va a bonos IEF
  5. Rebote de corto plazo RSI  -> compra SPY tras caídas fuertes de 1-3 días si la tendencia es alcista;
                                   vende cuando el precio supera su media de 5 días

Reglas comunes:
  - Las decisiones se toman con el precio de cierre y se ejecutan al cierre del DÍA SIGUIENTE (no se mira el futuro).
  - Cada compra/venta paga un costo (comisión + diferencia de precio) de 0.10% por defecto.
  - El efectivo no rinde intereses (supuesto conservador).
  - Precios ajustados por dividendos.

Uso:
  python comparador.py                       (división entrenamiento/prueba en 2018-01-01)
  python comparador.py --division 2015-01-01
  python comparador.py --demo                (datos simulados, sin internet)

Genera: comparacion.png (gráfico) y comparacion.csv (tabla).
Herramienta educativa. Resultados pasados no garantizan resultados futuros.
"""
import argparse
import sys

import numpy as np
import pandas as pd

DIAS_ANIO = 252
ACTIVOS = ["SPY", "EFA", "IEF", "SHY"]


# ============================================================ DATOS
def cargar_precios(args) -> pd.DataFrame:
    if args.demo:
        rng = np.random.default_rng(11)
        fechas = pd.bdate_range("2003-01-02", "2026-09-30")
        mu = {"SPY": 0.0004, "EFA": 0.00025, "IEF": 0.00015, "SHY": 0.00007}
        sd = {"SPY": 0.012, "EFA": 0.013, "IEF": 0.004, "SHY": 0.001}
        comun = rng.normal(0, 1, len(fechas))
        datos = {}
        for a in ACTIVOS:
            e = rng.normal(0, 1, len(fechas))
            corr = 0.8 if a in ("SPY", "EFA") else -0.2
            z = corr * comun + np.sqrt(1 - corr ** 2) * e
            datos[a] = 100 * np.exp(np.cumsum(mu[a] + sd[a] * z))
        return pd.DataFrame(datos, index=fechas)
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("Falta yfinance. Ejecuta primero 1_instalar_librerias.bat")
    df = yf.download(ACTIVOS, start="2002-08-01", auto_adjust=True, progress=False)["Close"]
    df = df[ACTIVOS].dropna()
    if df.empty:
        sys.exit("No se pudieron descargar los precios. Revisa tu conexión a internet.")
    return df


# ============================================================ HERRAMIENTAS
def fin_de_mes(precios: pd.DataFrame) -> pd.Series:
    """True en el último día hábil de cada mes."""
    m = pd.Series(precios.index.to_period("M"), index=precios.index)
    siguiente = m.shift(-1)
    # el último dato disponible solo es fin de mes si el próximo día hábil ya es otro mes
    siguiente.iloc[-1] = (precios.index[-1] + pd.offsets.BDay(1)).to_period("M")
    return m != siguiente


def mensual_a_diario(decisiones: pd.DataFrame, precios: pd.DataFrame) -> pd.DataFrame:
    """Mantiene la decisión de fin de mes durante todo el mes siguiente."""
    return decisiones.reindex(precios.index).ffill().fillna(0)


def rsi(precio: pd.Series, n: int) -> pd.Series:
    cambio = precio.diff()
    sube = cambio.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    baja = (-cambio.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + sube / baja.replace(0, np.nan))


def vacio(precios):
    return pd.DataFrame(0.0, index=precios.index, columns=ACTIVOS)


# ============================================================ ESTRATEGIAS
# Cada estrategia devuelve, para cada día, qué % del dinero va en cada activo (lo que falte = efectivo).

def comprar_y_mantener(p):
    w = vacio(p); w["SPY"] = 1.0
    return w


def cartera_60_40(p):
    fm = fin_de_mes(p)
    dec = vacio(p)[fm]
    dec["SPY"], dec["IEF"] = 0.6, 0.4
    return mensual_a_diario(dec, p)


def cruce_medias(p, rapida=50, lenta=200):
    w = vacio(p)
    w["SPY"] = (p["SPY"].rolling(rapida).mean() > p["SPY"].rolling(lenta).mean()).astype(float)
    return w


def filtro_tendencia(p, dias=200):
    fm = fin_de_mes(p)
    sobre = p["SPY"] > p["SPY"].rolling(dias).mean()
    dec = vacio(p)[fm]
    dec["SPY"] = sobre[fm].astype(float)
    dec["IEF"] = 1 - dec["SPY"]
    return mensual_a_diario(dec, p)


def rotacion_momentum(p, dias=252):
    fm = fin_de_mes(p)
    ret12 = p / p.shift(dias) - 1
    dec = vacio(p)[fm]
    for fecha in dec.index:
        r = ret12.loc[fecha]
        if r.isna().any():
            continue
        mejor = "SPY" if r["SPY"] >= r["EFA"] else "EFA"
        if r[mejor] > r["SHY"]:          # momentum absoluto: ¿le gana al "efectivo"?
            dec.loc[fecha, mejor] = 1.0
        else:
            dec.loc[fecha, "IEF"] = 1.0
    return mensual_a_diario(dec, p)


def rebote_rsi(p, entrada=10, tendencia=200, salida=5):
    spy = p["SPY"]
    r2 = rsi(spy, 2)
    media_t = spy.rolling(tendencia).mean()
    media_s = spy.rolling(salida).mean()
    w = vacio(p)
    dentro = False
    for i, fecha in enumerate(p.index):
        if pd.isna(media_t.iloc[i]):
            continue
        if not dentro and spy.iloc[i] > media_t.iloc[i] and r2.iloc[i] < entrada:
            dentro = True
        elif dentro and spy.iloc[i] > media_s.iloc[i]:
            dentro = False
        w.iloc[i, 0] = 1.0 if dentro else 0.0
    return w


ESTRATEGIAS = {
    "0. Comprar y mantener SPY": comprar_y_mantener,
    "1. Cartera 60/40": cartera_60_40,
    "2. Cruce de medias 50/200": cruce_medias,
    "3. Filtro de tendencia": filtro_tendencia,
    "4. Rotación por momentum": rotacion_momentum,
    "5. Rebote de corto plazo RSI": rebote_rsi,
}


# ============================================================ SIMULACIÓN Y MÉTRICAS
def simular(pesos: pd.DataFrame, precios: pd.DataFrame, costo: float) -> pd.Series:
    ret = precios.pct_change().fillna(0)
    pos = pesos.shift(1).fillna(0)                 # se ejecuta al día siguiente
    rotacion = pos.diff().abs().sum(axis=1)
    rotacion.iloc[0] = pos.iloc[0].abs().sum()
    return (pos * ret).sum(axis=1) - rotacion * costo, pos, rotacion


def metricas(ret: pd.Series, pos: pd.DataFrame, rot: pd.Series) -> dict:
    curva = (1 + ret).cumprod()
    anios = len(ret) / DIAS_ANIO
    cagr = curva.iloc[-1] ** (1 / anios) - 1
    vol = ret.std() * np.sqrt(DIAS_ANIO)
    dd = (curva / curva.cummax() - 1).min()
    return {
        "Rent. anual": cagr,
        "Volatilidad": vol,
        "Sharpe": (ret.mean() * DIAS_ANIO) / vol if vol > 0 else 0.0,
        "Peor caída": dd,
        "Calmar": cagr / abs(dd) if dd < 0 else 0.0,
        "% invertido": pos.sum(axis=1).clip(upper=1).mean(),
        "Operac./año": (rot > 0.01).sum() / anios,
        "S/10k ->": 10000 * curva.iloc[-1],
    }


def imprimir(titulo, filas):
    print(f"\n{titulo}")
    print(f"{'Estrategia':32}{'Rent.anual':>11}{'Volat.':>8}{'Sharpe':>8}{'PeorCaída':>11}"
          f"{'Calmar':>8}{'%Invert.':>9}{'Op/año':>8}{'10k ->':>11}")
    for nombre, m in filas.items():
        print(f"{nombre:32}{m['Rent. anual']:>+11.2%}{m['Volatilidad']:>8.1%}{m['Sharpe']:>8.2f}"
              f"{m['Peor caída']:>11.1%}{m['Calmar']:>8.2f}{m['% invertido']:>9.0%}"
              f"{m['Operac./año']:>8.1f}{m['S/10k ->']:>11,.0f}")


# ============================================================ PRINCIPAL
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--division", default="2018-01-01")
    ap.add_argument("--costo", type=float, default=0.001)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--sin-grafico", action="store_true")
    args = ap.parse_args()

    precios = cargar_precios(args)
    resultados = {}
    for nombre, f in ESTRATEGIAS.items():
        resultados[nombre] = simular(f(precios), precios, args.costo)

    # todas empiezan el mismo día: cuando ya hay 12 meses de historia para todas
    inicio = precios.index[260]
    d = pd.Timestamp(args.division)
    fuente = "DATOS SIMULADOS (demo)" if args.demo else "datos reales"
    print(f"=== Comparación de estrategias | {fuente} | costo {args.costo:.2%} por operación ===")
    print(f"Periodo analizado: {inicio.date()} a {precios.index[-1].date()} | "
          f"S/10k -> = cuánto valdrían 10,000 invertidos al inicio de cada periodo")

    tablas = []
    for titulo, desde, hasta in (("PERIODO COMPLETO", inicio, None),
                                 (f"ENTRENAMIENTO (hasta {d.date()})", inicio, d - pd.Timedelta(days=1)),
                                 (f"PRUEBA (desde {d.date()}) — ESTA ES LA QUE IMPORTA", d, None)):
        filas = {n: metricas(r.loc[desde:hasta], pos.loc[desde:hasta], rot.loc[desde:hasta])
                 for n, (r, pos, rot) in resultados.items()}
        imprimir(titulo, filas)
        t = pd.DataFrame(filas).T
        t.insert(0, "Periodo", titulo)
        tablas.append(t)
    pd.concat(tablas).round(4).to_csv("comparacion.csv", encoding="utf-8-sig")
    print("\nTabla guardada en comparacion.csv")

    if not args.sin_grafico:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        colores = ["#9AA5B1", "#B08D57", "#1F3A5F", "#2E86AB", "#C0392B", "#27AE60"]
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                     gridspec_kw={"height_ratios": [3, 1.3]})
        for (nombre, (r, _, _)), c in zip(resultados.items(), colores):
            curva = 10000 * (1 + r.loc[inicio:]).cumprod()
            a1.plot(curva, label=nombre, color=c, lw=2.2 if nombre.startswith("0") else 1.4)
            a2.plot(curva / curva.cummax() - 1, color=c, lw=1)
        a1.set_yscale("log")
        a1.set_title("Cuánto valdrían 10,000 invertidos en cada estrategia (escala logarítmica)")
        a1.legend(frameon=False, fontsize=9)
        a1.grid(alpha=0.2)
        a2.set_title("Caída desde el máximo anterior", fontsize=10)
        a2.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        a2.grid(alpha=0.2)
        for a in (a1, a2):
            a.axvline(d, color="black", ls="--", lw=1)
        a1.text(d, a1.get_ylim()[1], "  inicio de la PRUEBA", va="top", fontsize=9)
        fig.tight_layout()
        fig.savefig("comparacion.png", dpi=130)
        print("Gráfico guardado en comparacion.png")


if __name__ == "__main__":
    main()
