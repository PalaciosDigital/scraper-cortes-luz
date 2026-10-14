"""Publicación en S3."""
from __future__ import annotations

import json
from datetime import datetime

import boto3
from botocore.exceptions import ClientError


class S3:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.bucket = cfg["bucket"]
        self.prefijo = cfg["prefijo"].strip("/")
        self.cliente = boto3.client("s3", region_name=cfg.get("region", "us-east-1"))

    def _clave(self, nombre: str) -> str:
        return f"{self.prefijo}/{nombre}"

    def leer_json(self, nombre: str):
        try:
            obj = self.cliente.get_object(Bucket=self.bucket, Key=self._clave(nombre))
            return json.loads(obj["Body"].read())
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise

    def escribir_json(self, nombre: str, datos, cache: str | None = None) -> str:
        cuerpo = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.cliente.put_object(
            Bucket=self.bucket, Key=self._clave(nombre), Body=cuerpo,
            ContentType="application/json; charset=utf-8",
            CacheControl=cache or self.cfg.get("cache_control", "public, max-age=300"),
        )
        return f"https://{self.bucket}.s3.{self.cfg.get('region', 'us-east-1')}.amazonaws.com/{self._clave(nombre)}"

    def publicar(self, registros: list[dict], estado: dict, produccion: bool) -> dict:
        sello = datetime.now().strftime("%Y-%m-%d_%H%M")
        destino = self.cfg["actual"] if produccion else self.cfg["staging"]
        urls = {
            "historico": self.escribir_json(f"{self.cfg['historico']}/cortes_luz_{sello}.json", registros,
                                            cache="public, max-age=31536000, immutable"),
            "destino": self.escribir_json(destino, registros),
        }
        self.escribir_json(self.cfg["estado"], {**estado, "destino": "produccion" if produccion else "staging"},
                           cache="no-cache")
        return urls
