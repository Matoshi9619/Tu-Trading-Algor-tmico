"""
VELAS — precios durante el día para el simulador.
Se ejecuta cada hora mientras la bolsa de Nueva York está abierta (GitHub Actions).
Guarda docs/velas.json con velas de 15 minutos, 1 hora, 1 día y 1 semana para los 4 fondos.
Si un fondo falla, conserva los datos anteriores de ese fondo.
"""
import json
import os
from datetime import datetime, timezone

import yfinance as yf

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "docs", "velas.json")
ACTIVOS = ["SPY", "EFA", "IEF", "SHY"]
# clave: (intervalo de yfinance, periodo a descargar, máximo de velas a guardar, ¿es diario?)
CONF = {
    "15m": ("15m", "5d", 140, False),
    "1h": ("1h", "1mo", 160, False),
    "1d": ("1d", "1y", 260, True),
    "1wk": ("1wk", "5y", 262, True),
}


def bajar(ticker: str) -> dict:
    tk = yf.Ticker(ticker)
    out = {}
    for clave, (iv, periodo, maximo, diario) in CONF.items():
        h = tk.history(period=periodo, interval=iv, auto_adjust=False, prepost=False)
        h = h.dropna(subset=["Open", "High", "Low", "Close"]).tail(maximo)
        if h.empty:
            raise RuntimeError(f"sin datos {ticker} {iv}")
        filas = []
        for ts, r in h.iterrows():
            if diario:
                txt = ts.strftime("%Y-%m-%d")
            else:  # hora de Lima
                txt = ts.tz_convert("America/Lima").strftime("%Y-%m-%d %H:%M")
            filas.append([txt, round(float(r["Open"]), 2), round(float(r["High"]), 2),
                          round(float(r["Low"]), 2), round(float(r["Close"]), 2)])
        out[clave] = filas
    return out


def main():
    anterior = {}
    if os.path.exists(SALIDA):
        try:
            anterior = json.load(open(SALIDA, encoding="utf-8")).get("velas", {})
        except Exception:
            anterior = {}
    velas, errores = {}, []
    for t in ACTIVOS:
        try:
            velas[t] = bajar(t)
        except Exception as e:  # conserva lo anterior
            errores.append(f"{t}: {e}")
            if t in anterior:
                velas[t] = anterior[t]
    if not velas:
        raise SystemExit("No se pudo descargar ningún fondo: " + "; ".join(errores))
    datos = {"actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "velas": velas}
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(datos, f, separators=(",", ":"))
    print(f"OK velas -> {SALIDA} ({os.path.getsize(SALIDA) / 1024:.0f} KB)")
    for t in velas:
        print(t, {k: (len(v), v[-1][0], v[-1][4]) for k, v in velas[t].items()})
    if errores:
        print("Avisos:", errores)


if __name__ == "__main__":
    main()
