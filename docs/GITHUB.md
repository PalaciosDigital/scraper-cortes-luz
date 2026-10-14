# Puesta en marcha en GitHub

Repositorio local ya preparado: `~/repos/scraper-cortes-luz` (fuera de iCloud, con
el primer commit hecho). Estos pasos se hacen una sola vez.

## 1. Elegir la cuenta

El repositorio debe ser **público**: raw.githubusercontent.com solo sirve repos
privados con token, y el buscador no puede llevar un token.

- Si va en la cuenta de Mazar (`tefaceli`), quien la administre debe crearlo o
  darte acceso de colaborador (Settings → Collaborators).
- Si va en tu cuenta o en una organización de PRIMICIAS, puedes hacerlo tú.

## 2. Subir el repositorio (GitHub Desktop, sin terminal)

1. Instala GitHub Desktop (desktop.github.com) e inicia sesión con la cuenta elegida.
2. **File → Add local repository…** → elige `~/repos/scraper-cortes-luz`.
3. Pulsa **Publish repository**.
   - Name: `scraper-cortes-luz`
   - **Desmarca "Keep this code private"**.
   - Organization: la cuenta u organización elegida.
4. Al terminar, la web del repo muestra los archivos.

Alternativa por terminal (requiere un token personal como contraseña):

```bash
cd ~/repos/scraper-cortes-luz
git remote add origin https://github.com/<cuenta>/scraper-cortes-luz.git
git push -u origin main
```

## 3. Permitir que el workflow escriba en el repo

En la web del repo: **Settings → Actions → General**

- Actions permissions: **Allow all actions and reusable workflows**.
- Workflow permissions: **Read and write permissions** → **Save**.

Sin esto, el workflow no puede hacer commit de `data/` ni abrir issues.

## 4. Recibir los avisos por correo

Botón **Watch** (arriba a la derecha) → **Custom** → marca **Issues** → Apply.
Cada aviso (datos nuevos o revisión) llega como un issue a tu correo.

## 5. Primera ejecución manual

**Actions → Vigilar cortes de luz → Run workflow → Run workflow**.

Debe terminar en verde. Como la línea base ya va en el repo
(`data/vigilancia/estado.json`), lo normal es "Sin cambios en data/".
A partir de aquí corre solo cada 3 horas (6:00–22:00 de Ecuador). GitHub puede
retrasar los cron unos minutos.

## 6. Conectar el buscador

La URL que lee el buscador será:

```
https://raw.githubusercontent.com/<cuenta>/scraper-cortes-luz/main/data/cortes_luz_publicado.json
```

Hasta la primera aprobación ese archivo no existe; el buscador usa entonces su
copia embebida, igual que hoy. Pasos (con Claude):

1. Cambiar `DATA_URL` en `01_HTML/PROTOTIPO.html` a esa URL.
2. `/inyecta_a_Xalok` y pegarlo en el artículo **una sola vez**.

## Día a día

| Pasa esto | Haz esto |
|---|---|
| Llega un issue **"Datos nuevos"** | Abre `data/cortes_luz_vigentes.json` en el repo y revisa. Luego **Actions → Aprobar publicación → Run workflow**, marca la casilla de confirmación y pulsa Run. En ≤ 5 min está en el buscador. Cierra el issue. |
| Llega un issue **"Revisión necesaria"** | Léelo: formato desconocido, filas descartadas, página cambiada o caída. Pásaselo a Claude: "Retomemos el pipeline de cortes de luz, llegó este aviso: …". |
| Cambia la página oficial | Edita `config.yaml` desde la web (lápiz ✏️ → Commit changes). La primera pasada sobre la URL nueva registra lo existente como línea base. Si ya hay un cronograma vigente que quieres publicar, pide a Claude una primera carga con `--simular`. |
| El flujo ya es confiable | En `config.yaml`, cambia `publicacion: revision` por `publicacion: directa`. Los datos nuevos válidos se publican sin aprobación (con código 20 nunca se publica). |
| Una ejecución sale en rojo | Abre la ejecución en Actions, copia el error y pásaselo a Claude. |

## Notas

- GitHub desactiva los cron de repos públicos tras 60 días sin commits. El
  workflow deja un latido (`data/latido.txt`) si pasan 30 días sin cambios.
- No edites a mano lo que hay en `data/`, salvo `cantones_ecuador.csv`.
