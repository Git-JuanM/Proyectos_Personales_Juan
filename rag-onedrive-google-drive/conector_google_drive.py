"""Conector de Google Drive (Drive API v3).

Hace dos cosas: iniciar sesión con la cuenta de Google y listar/descargar los
archivos de las carpetas configuradas en GDRIVE_FOLDERS.

Solo pide permiso de lectura (drive.readonly): no puede modificar ni borrar nada.
"""
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import config
from sincronizar import ArchivoRemoto, carpeta_fuente

FUENTE = "google_drive"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

TIPO_CARPETA = "application/vnd.google-apps.folder"

# Los documentos nativos de Google no son archivos: hay que exportarlos.
# tipo de Google -> (formato de exportación, extensión con la que se guarda)
EXPORTAR = {
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("text/plain", ".txt"),
}


## Inicio de sesión
def obtener_servicio():
    """Devuelve el cliente de la API de Drive con la sesión iniciada.

    La primera vez abre el navegador para iniciar sesión. Después reutiliza la
    sesión guardada en datos/google_drive/token.json.
    """
    if not config.GDRIVE_CREDENTIALS_FILE.exists():
        raise RuntimeError(
            f"No se encuentra {config.GDRIVE_CREDENTIALS_FILE.name}. "
            "Descárgalo de Google Cloud y guárdalo en la carpeta del proyecto."
        )

    ruta_token = carpeta_fuente(FUENTE) / "token.json"
    creds = None

    if ruta_token.exists():
        creds = Credentials.from_authorized_user_file(str(ruta_token), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(config.GDRIVE_CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        # Guarda la sesión para la próxima ejecución
        ruta_token.parent.mkdir(parents=True, exist_ok=True)
        ruta_token.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds)


def extraer_id(valor):
    """Acepta el id de una carpeta o su enlace completo y devuelve el id."""
    valor = valor.strip()
    coincidencia = re.search(r"/folders/([A-Za-z0-9_-]+)", valor) or re.search(r"[?&]id=([A-Za-z0-9_-]+)", valor)
    return coincidencia.group(1) if coincidencia else valor


## Llamadas a la API de Drive
def _hijos(servicio, id_carpeta):
    """Devuelve todos los elementos de una carpeta, siguiendo la paginación."""
    token_pagina = None
    while True:
        respuesta = servicio.files().list(
            q=f"'{id_carpeta}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, md5Checksum, webViewLink)",
            pageSize=1000,
            pageToken=token_pagina,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        yield from respuesta.get("files", [])
        token_pagina = respuesta.get("nextPageToken")
        if not token_pagina:
            break


def _descargador(servicio, id_archivo, tipo_exportacion=None):
    def descargar(destino):
        if tipo_exportacion:
            peticion = servicio.files().export_media(fileId=id_archivo, mimeType=tipo_exportacion)
        else:
            peticion = servicio.files().get_media(fileId=id_archivo)

        with open(destino, "wb") as salida:
            descarga = MediaIoBaseDownload(salida, peticion)
            terminado = False
            while not terminado:
                _, terminado = descarga.next_chunk()
    return descargar


## Listado de archivos
def listar_archivos(carpetas=None, servicio=None):
    """Lista los archivos de las carpetas configuradas, incluidas sus subcarpetas."""
    carpetas = config.GDRIVE_FOLDERS if carpetas is None else carpetas
    if not carpetas:
        raise RuntimeError("Define al menos una carpeta en GDRIVE_FOLDERS (archivo .env).")
    servicio = servicio or obtener_servicio()

    archivos = []
    for carpeta in carpetas:
        id_raiz = extraer_id(carpeta)
        nombre_raiz = servicio.files().get(
            fileId=id_raiz, fields="name", supportsAllDrives=True
        ).execute()["name"]
        pendientes = [(id_raiz, nombre_raiz)]

        while pendientes:
            id_carpeta, ruta = pendientes.pop()
            for item in _hijos(servicio, id_carpeta):
                ruta_item = f"{ruta}/{item['name']}"
                tipo = item["mimeType"]

                if tipo == TIPO_CARPETA:
                    pendientes.append((item["id"], ruta_item))
                    continue

                tipo_exportacion, extension = EXPORTAR.get(tipo, (None, ""))
                if tipo.startswith("application/vnd.google-apps.") and not tipo_exportacion:
                    extension = ".google"     # Formularios, mapas, accesos directos: no se indexan

                archivos.append(ArchivoRemoto(
                    id=item["id"],
                    nombre=item["name"],
                    ruta=f"Google Drive/{ruta_item}",
                    version=item.get("md5Checksum") or item.get("modifiedTime", ""),
                    url=item.get("webViewLink", ""),
                    extension=extension,
                    descargar=_descargador(servicio, item["id"], tipo_exportacion),
                ))
    return archivos
