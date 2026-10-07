"""Sincronización: mantiene el índice al día con las carpetas de la nube.

Los conectores (OneDrive, Google Drive, carpeta local) solo saben listar y
descargar archivos. Este módulo decide qué hacer con cada uno:

- archivo nuevo o modificado -> se descarga y se vuelve a indexar,
- archivo sin cambios        -> no se toca,
- archivo que ya no está     -> se borran sus fragmentos del índice.

Para saber qué cambió se guarda un registro (manifest.json) con la versión de
cada archivo ya indexado.
"""
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import config
import rag_core


# Cuántos archivos omitidos o con error se detallan en el resumen
MAX_DETALLE = 20


@dataclass
class ArchivoRemoto:
    """Un archivo de la nube, tal como lo describe un conector."""
    id: str                               # Identificador único en la nube
    nombre: str                           # Nombre del archivo
    ruta: str                             # Ruta legible, para mostrar como fuente
    version: str                          # Cambia cuando cambia el contenido
    descargar: Callable[[Path], None]     # Función que guarda el archivo en disco
    url: str = ""                         # Enlace para abrirlo en el navegador
    extension: str = ""                   # Extensión con la que se guarda (si no es la del nombre)

    def __post_init__(self):
        if not self.extension:
            self.extension = Path(self.nombre).suffix.lower()


@dataclass
class Resumen:
    indexados: list = field(default_factory=list)
    sin_cambios: int = 0
    eliminados: list = field(default_factory=list)
    omitidos: list = field(default_factory=list)      # (ruta, motivo)
    errores: list = field(default_factory=list)       # (ruta, error)
    fragmentos: int = 0

    def __str__(self):
        lineas = [
            f"Archivos indexados (nuevos o modificados): {len(self.indexados)}",
            f"Archivos sin cambios: {self.sin_cambios}",
            f"Archivos eliminados del índice: {len(self.eliminados)}",
            f"Archivos omitidos: {len(self.omitidos)}",
            f"Archivos con error: {len(self.errores)}",
            f"Fragmentos en el índice: {self.fragmentos}",
        ]
        for ruta, motivo in self.omitidos[:MAX_DETALLE]:
            lineas.append(f"  omitido: {ruta} ({motivo})")
        if len(self.omitidos) > MAX_DETALLE:
            lineas.append(f"  ... y {len(self.omitidos) - MAX_DETALLE} omitidos más")
        for ruta, error in self.errores[:MAX_DETALLE]:
            lineas.append(f"  error:   {ruta} ({error})")
        return "\n".join(lineas)


def carpeta_fuente(fuente):
    """Carpeta local de una fuente: datos/onedrive, datos/google_drive..."""
    return config.DATA_DIR / fuente


def carpeta_indice(fuente):
    return carpeta_fuente(fuente) / "chroma"


def borrar_indice(fuente):
    """Borra el índice y las copias locales de una fuente (no las credenciales)."""
    base = carpeta_fuente(fuente)
    for nombre in ("chroma", "archivos"):
        shutil.rmtree(base / nombre, ignore_errors=True)
    (base / "manifest.json").unlink(missing_ok=True)


def sincronizar(fuente, archivos, avisar=print):
    """Pone al día el índice de `fuente` con la lista de archivos remotos."""
    base = carpeta_fuente(fuente)
    carpeta_archivos = base / "archivos"
    carpeta_archivos.mkdir(parents=True, exist_ok=True)
    ruta_manifest = base / "manifest.json"

    manifest = _leer_manifest(ruta_manifest)
    embedding_actual = rag_core.nombre_embedding()
    if manifest["archivos"] and manifest.get("embedding") != embedding_actual:
        raise RuntimeError(
            "El índice se creó con otro modelo de embeddings "
            f"({manifest.get('embedding')}). Ejecuta de nuevo con --reindexar."
        )
    manifest["embedding"] = embedding_actual

    vectordb = rag_core.vector_database(carpeta_indice(fuente))
    resumen = Resumen()
    vistos = set()

    for archivo in archivos:
        if archivo.nombre.startswith(("~$", ".")):
            continue      # Archivos temporales u ocultos
        if archivo.extension not in rag_core.EXTENSIONES:
            resumen.omitidos.append((archivo.ruta, "tipo de archivo no soportado"))
            continue

        vistos.add(archivo.id)
        anterior = manifest["archivos"].get(archivo.id)
        if anterior and anterior["version"] == archivo.version:
            resumen.sin_cambios += 1
            continue

        avisar(f"Indexando: {archivo.ruta}")
        destino = carpeta_archivos / (_nombre_seguro(archivo.id) + archivo.extension)
        try:
            archivo.descargar(destino)
            if anterior:
                rag_core.eliminar_fragmentos(vectordb, anterior["ids"])
                del manifest["archivos"][archivo.id]
            metadatos = {
                "source": archivo.ruta,
                "nombre": archivo.nombre,
                "url": archivo.url,
                "id_archivo": archivo.id,
            }
            ids = rag_core.indexar_archivo(vectordb, destino, metadatos, archivo.id)
        except Exception as error:
            resumen.errores.append((archivo.ruta, str(error)))
            _guardar_manifest(ruta_manifest, manifest)
            continue

        if not ids:
            resumen.omitidos.append((archivo.ruta, "no se pudo extraer texto"))
        else:
            resumen.indexados.append(archivo.ruta)

        manifest["archivos"][archivo.id] = {
            "ruta": archivo.ruta,
            "version": archivo.version,
            "local": destino.name,
            "ids": ids,
        }
        # Se guarda tras cada archivo: si el proceso se interrumpe, no se pierde lo hecho
        _guardar_manifest(ruta_manifest, manifest)

    # Archivos que estaban indexados y ya no existen en la nube
    for id_archivo in set(manifest["archivos"]) - vistos:
        registro = manifest["archivos"].pop(id_archivo)
        rag_core.eliminar_fragmentos(vectordb, registro["ids"])
        (carpeta_archivos / registro["local"]).unlink(missing_ok=True)
        resumen.eliminados.append(registro["ruta"])

    _guardar_manifest(ruta_manifest, manifest)
    resumen.fragmentos = rag_core.cantidad_fragmentos(vectordb)
    return resumen


def _leer_manifest(ruta):
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return {"embedding": None, "archivos": {}}


def _guardar_manifest(ruta, manifest):
    ruta.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")


def _nombre_seguro(texto):
    """Convierte un id de la nube en un nombre de archivo válido."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", texto)[:120]
