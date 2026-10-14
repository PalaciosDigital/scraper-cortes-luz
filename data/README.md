# Catálogo de cantones

`cantones_ecuador.csv` es **parcial**: solo trae los cantones que aparecieron en
el JSON de mayo-junio 2026. Hay que completarlo con la División Político
Administrativa oficial del INEC (24 provincias, 221 cantones).

Columnas:

- `canton`: como puede aparecer en el PDF (se compara sin tildes ni mayúsculas).
- `provincia`: provincia política en mayúsculas.
- `canton_oficial` (opcional): nombre normalizado cuando `canton` es un alias o
  una grafía alternativa. Ej.: `Macas` → `Morona`, `Quininde` → `Quinindé`.

Hay cantones homónimos en distintas provincias (Bolívar en Carchi y Manabí,
Olmedo en Loja y Manabí). Se pueden repetir filas; el normalizador elige la que
coincide con la provincia del PDF.
