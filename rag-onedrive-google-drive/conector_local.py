"""Conector de carpeta local.

Sirve para probar el sistema sin configurar ninguna nube: lee las carpetas del
computador definidas en LOCAL_FOLDERS. También funciona con la carpeta que
OneDrive o Google Drive sincronizan en el computador.
"""
import shutil
from pathlib import Path

import config
from sincronizar import ArchivoRemoto

FUENTE = "local"


def listar_archivos(carpetas=None):
    """Lista los archivos de las carpetas configuradas, incluidas sus subcarpetas."""
    carpetas = config.LOCAL_FOLDERS if carpetas is None else carpetas
    if not carpetas:
        raise RuntimeError("Define al menos una carpeta en LOCAL_FOLDERS (archivo .env).")

    archivos = []
    for carpeta in carpetas:
        raiz = Path(carpeta).expanduser()
        if not raiz.is_dir():
            raise FileNotFoundError(f"No existe la carpeta: {raiz}")

        for ruta in sorted(raiz.rglob("*")):
            if not ruta.is_file():
                continue
            estado = ruta.stat()
            archivos.append(ArchivoRemoto(
                id=str(ruta.resolve()),
                nombre=ruta.name,
                ruta=f"{raiz.name}/{ruta.relative_to(raiz).as_posix()}",
                version=f"{estado.st_mtime_ns}-{estado.st_size}",
                descargar=lambda destino, origen=ruta: shutil.copyfile(origen, destino),
            ))
    return archivos
