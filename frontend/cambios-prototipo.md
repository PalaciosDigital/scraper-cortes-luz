# Cambios en el buscador (HTML en Xalok)

El HTML no vive en este repositorio. Estos son los cambios a aplicar en el
script del elemento interactivo (`#pcl-app`). Para trabajarlos con el agente,
descarga el prototipo con `bash scripts/descargar_linea_base.sh` y edita
`linea_base/PROTOTIPO.html`.

Recuerda: sin `innerHTML` (el sanitizador de Xalok lo elimina). Solo `createElement`.

## 1. URL estable

```js
// Antes
var DATA_URL = 'https://primicias.s3.us-east-1.amazonaws.com/editorial/2026/Cortes+de+Luz+2026/cortes_luz_mayo_junio_2026.json';
// Después
var DATA_URL = 'https://primicias.s3.us-east-1.amazonaws.com/editorial/2026/Cortes+de+Luz+2026/cortes_luz_actual.json';
```

## 2. Respaldo que no muestre datos vencidos

Hoy, si el fetch falla, `arrancar(DATA)` muestra la copia embebida aunque sea
de hace meses. Propuesta: usar la copia solo si tiene fechas vigentes; si no,
mostrar un aviso.

```js
function vigentes(rows) {
  var hoy = new Date().toISOString().slice(0, 10);
  return rows.filter(function (r) { return r.fecha >= hoy; });
}
function respaldo() {
  var v = vigentes(DATA);
  if (v.length) arrancar(v);
  else mostrarAviso('No pudimos cargar los horarios. Consulta los canales oficiales de tu distribuidora.');
}
// Reemplaza cada arrancar(DATA) por respaldo()
```

`mostrarAviso` debe crear el mensaje con `createElement` dentro de `#pcl-app`.

## 3. Timeout

2,5 s es corto para datos móviles en Ecuador. Subir a 6 s y mostrar un
estado de carga en el selector de provincia mientras tanto.

## 4. Filtro por cantón con `cantones[]`

Los registros nuevos traen `cantones: ["Samborondón", "Daule", …]`. Al
construir el índice, registrar el corte bajo **cada** cantón de la lista
(si existe) en lugar del texto de `canton`. Mantener compatibilidad: si
`cantones` no existe, usar `canton`.

```js
var lista = (r.cantones && r.cantones.length) ? r.cantones : [r.canton];
lista.forEach(function (c) { /* indexar r bajo provincia → c */ });
```

## 5. Fecha de actualización visible

Leer `estado.json` (mismo prefijo) y mostrar "Actualizado el 14 de octubre,
09:30" junto a la fuente. Si falla, no mostrar nada.

## Verificación

1. Con CORS activado, abrir el artículo en Xalok (preview) en móvil.
2. En DevTools → Network: `cortes_luz_actual.json` debe responder 200 **sin**
   error CORS.
3. Bloquear la URL en DevTools y recargar: debe verse el aviso (o los datos
   vigentes de la copia embebida), nunca cortes pasados.
