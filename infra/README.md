# Infraestructura AWS

Pasos de una sola vez. Requieren permisos de administrador del bucket.

## 1. CORS en el bucket

Permite que el buscador dentro de Xalok (primicias.ec) lea el JSON vivo.

> Atención: `put-bucket-cors` **reemplaza** toda la configuración CORS del
> bucket. Revisa primero si ya existe una y combínalas.

```bash
aws s3api get-bucket-cors --bucket primicias            # ¿hay reglas previas?
aws s3api put-bucket-cors --bucket primicias --cors-configuration file://infra/cors.json
```

Verificación:

```bash
curl -sI -H "Origin: https://www.primicias.ec" \
  "https://primicias.s3.us-east-1.amazonaws.com/editorial/2026/Cortes+de+Luz+2026/cortes_luz_mayo_junio_2026.json" \
  | grep -i access-control
```

Debe aparecer `access-control-allow-origin: https://www.primicias.ec`.

## 2. Usuario IAM del pipeline

Usuario `pipeline-cortes-luz` con la política `iam-policy.json`: solo puede
leer y escribir dentro de la carpeta de cortes de luz.

```bash
aws iam create-user --user-name pipeline-cortes-luz
aws iam put-user-policy --user-name pipeline-cortes-luz \
  --policy-name cortes-luz-s3 --policy-document file://infra/iam-policy.json
aws iam create-access-key --user-name pipeline-cortes-luz
```

Las llaves van en `.env` (local) y en los secretos del repositorio de GitHub.
Nunca en el código.

## 3. (Opcional) CloudFront

Si el tráfico crece, servir el JSON por CloudFront reduce costo y latencia.
Con `Cache-Control: max-age=300` el contenido se renueva cada 5 minutos.
