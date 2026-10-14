# Esquema de datos

El archivo publicado es un **arreglo** de registros. Cada registro es un corte
programado para un alimentador en una fecha y franja horaria.

| Campo | Obligatorio | Ejemplo | Notas |
|---|---|---|---|
| `provincia` | sí | `AZUAY` | Mayúsculas. Provincia política (corregida por cantón). |
| `canton` | sí | `Cuenca` | Texto original; puede tener varios cantones. |
| `alimentador` | sí | `0823: Turi Sector Patamaba` | Código y nombre del alimentador. |
| `fecha` | sí | `2026-06-06` | ISO `AAAA-MM-DD`. |
| `dia` | sí | `Sábado` | Coincide con `fecha`; se recalcula, no se copia del PDF. |
| `horario` | sí | `09:00 a 13:00` | `HH:MM a HH:MM`. Puede cruzar medianoche. |
| `tipo_trabajo` | sí | `Cambio de equipos en medio voltaje` | |
| `zona_cortes` | sí | `0823: Turi Sector Patamaba` | Puede diferir de `alimentador`. |
| `sectores` | sí | `Yaritzagua, El Descanso, El Molino` | Lista separada por comas; el buscador busca aquí. |
| `cantones` | nuevo | `["Samborondón", "Daule"]` | Cantones separados y normalizados. |
| `provincia_original` | nuevo | `SUCUMBÍOS` | Solo si se corrigió la provincia. |
| `distribuidora` | nuevo | `CNEL Sucumbíos` | Si el PDF lo indica. |

Regla de compatibilidad: los nueve campos originales no se renombran ni se
eliminan, porque el buscador publicado los usa.

## Archivo de estado (`estado.json`)

```json
{
  "pdf_sha256": "…",
  "pdf_url": "…",
  "procesado_en": "2026-10-14T09:30:00-05:00",
  "registros": 107,
  "desde": "2026-05-30",
  "hasta": "2026-06-07",
  "destino": "staging",
  "advertencias": []
}
```
