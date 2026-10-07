"""Conector de OneDrive (Microsoft Graph).

Hace dos cosas: iniciar sesión con la cuenta de Microsoft y listar/descargar
los archivos de las carpetas configuradas en ONEDRIVE_FOLDERS.

Solo pide permiso de lectura (Files.Read): no puede modificar ni borrar nada.
"""
import time
from urllib.parse import quote

import msal
import requests

import config
from sincronizar import ArchivoRemoto, carpeta_fuente

FUENTE = "onedrive"
GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["Files.Read"]
CAMPOS = "id,name,size,file,folder,lastModifiedDateTime,webUrl,cTag,eTag"


## Inicio de sesión
def obtener_token():
    """Devuelve un token de acceso válido.

    La primera vez abre el navegador para iniciar sesión. Después reutiliza la
    sesión guardada en datos/onedrive/token_cache.json y la renueva sola.
    """
    if not config.ONEDRIVE_CLIENT_ID:
        raise RuntimeError("Falta ONEDRIVE_CLIENT_ID en el archivo .env.")

    ruta_cache = carpeta_fuente(FUENTE) / "token_cache.json"
    cache = msal.SerializableTokenCache()
    if ruta_cache.exists():
        cache.deserialize(ruta_cache.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        config.ONEDRIVE_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{config.ONEDRIVE_TENANT}",
        token_cache=cache,
    )

    result = None
    accounts = app.get_accounts()
    if accounts:
        # Ya hay una sesión guardada: se renueva sin preguntar nada
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        if config.ONEDRIVE_AUTH == "codigo":
            # Muestra un código para escribirlo en https://microsoft.com/devicelogin
            flow = app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise RuntimeError(f"No se pudo iniciar sesión: {flow.get('error_description', flow)}")
            print(flow["message"], flush=True)
            result = app.acquire_token_by_device_flow(flow)
        else:
            # Abre el navegador para iniciar sesión
            result = app.acquire_token_interactive(scopes=SCOPES)

    if "access_token" not in result:
        raise RuntimeError(
            f"No se pudo iniciar sesión en Microsoft: {result.get('error_description', result.get('error'))}"
        )

    if cache.has_state_changed:
        ruta_cache.parent.mkdir(parents=True, exist_ok=True)
        ruta_cache.write_text(cache.serialize(), encoding="utf-8")

    return result["access_token"]


## Llamadas a Microsoft Graph
def _get(url, obtener_token, params=None, stream=False):
    """GET con el token de acceso. Reintenta si Microsoft pide esperar."""
    for intento in range(5):
        respuesta = requests.get(
            url,
            headers={"Authorization": f"Bearer {obtener_token()}"},
            params=params,
            stream=stream,
            timeout=60,
        )
        if respuesta.status_code in (429, 503):
            time.sleep(int(respuesta.headers.get("Retry-After", 2 ** intento)))
            continue
        if respuesta.status_code == 404:
            raise FileNotFoundError(url)
        if respuesta.status_code in (401, 403):
            raise PermissionError(
                "Microsoft rechazó la petición. Revisa que la aplicación tenga el permiso Files.Read "
                "y borra datos/onedrive/token_cache.json para iniciar sesión de nuevo."
            )
        respuesta.raise_for_status()
        return respuesta
    raise RuntimeError("Microsoft Graph no respondió después de varios intentos.")


def _hijos(url, obtener_token):
    """Devuelve todos los elementos de una carpeta, siguiendo la paginación."""
    params = {"$select": CAMPOS, "$top": 200}
    while url:
        datos = _get(url, obtener_token, params=params).json()
        yield from datos.get("value", [])
        url = datos.get("@odata.nextLink")   # Enlace a la página siguiente, si hay
        params = None                         # El enlace ya trae los parámetros


def _url_carpeta(ruta):
    ruta = ruta.strip().strip("/\\").replace("\\", "/")
    if not ruta:
        return f"{GRAPH}/me/drive/root/children"
    return f"{GRAPH}/me/drive/root:/{quote(ruta)}:/children"


def _descargador(id_archivo, obtener_token):
    def descargar(destino):
        respuesta = _get(f"{GRAPH}/me/drive/items/{id_archivo}/content", obtener_token, stream=True)
        with open(destino, "wb") as salida:
            for bloque in respuesta.iter_content(chunk_size=1024 * 1024):
                salida.write(bloque)
    return descargar


## Listado de archivos
def listar_archivos(carpetas=None, obtener_token=obtener_token):
    """Lista los archivos de las carpetas configuradas, incluidas sus subcarpetas."""
    carpetas = config.ONEDRIVE_FOLDERS if carpetas is None else carpetas
    if not carpetas:
        raise RuntimeError("Define al menos una carpeta en ONEDRIVE_FOLDERS (archivo .env).")

    archivos = []
    for carpeta in carpetas:
        nombre_carpeta = carpeta.strip().strip("/\\").replace("\\", "/")
        pendientes = [(_url_carpeta(carpeta), nombre_carpeta)]

        while pendientes:
            url, ruta = pendientes.pop()
            try:
                elementos = list(_hijos(url, obtener_token))
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"No se encontró la carpeta '{ruta or carpeta}' en OneDrive. "
                    "Revisa ONEDRIVE_FOLDERS: la ruta va desde la raíz de OneDrive, por ejemplo Documentos/Contratos."
                ) from None
            for item in elementos:
                ruta_item = f"{ruta}/{item['name']}" if ruta else item["name"]

                if "folder" in item:
                    pendientes.append((f"{GRAPH}/me/drive/items/{item['id']}/children", ruta_item))
                elif "file" in item:
                    archivos.append(ArchivoRemoto(
                        id=item["id"],
                        nombre=item["name"],
                        ruta=f"OneDrive/{ruta_item}",
                        version=item.get("cTag") or item.get("eTag") or item.get("lastModifiedDateTime", ""),
                        url=item.get("webUrl", ""),
                        descargar=_descargador(item["id"], obtener_token),
                    ))
    return archivos
