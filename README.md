# Trading Algorítmico

App familiar para aprender a invertir **sin dinero real**, con precios reales de la bolsa.

- **¿Cómo está el mercado hoy?** Semáforo y precios explicados en palabras sencillas.
- **Competencia de robots:** 6 estrategias con US$ 10,000 ficticios cada una, desde el día en que se publicó la app.
- **Historia de 20 años:** cómo les fue a las estrategias desde 2004, incluidas las crisis de 2008, 2020 y 2022.
- **¿Y si hubiera invertido?:** calculadora con precios reales.

## Cómo funciona

- `docs/` es la app (GitHub Pages la publica). `docs/data.json` son los datos que muestra.
- `motor/actualizar.py` descarga los precios y recalcula todo.
- `.github/workflows/actualizar.yml` lo ejecuta solo de lunes a viernes a las 5:30 p.m. (hora de Lima).
  Para actualizar a mano: pestaña **Actions** → **Actualizar datos de la app** → **Run workflow**.
- `motor/estado_robots.json` guarda las carteras de los robots. Si se borra, la competencia empieza de cero.

## Instalar en Android

Abrir la dirección de la app en **Chrome** → menú **⋮** → **Agregar a la pantalla principal** (o **Instalar app**).

---
Práctica educativa. No es una recomendación de inversión.
