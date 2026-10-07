"""Pruebas de los conectores con respuestas simuladas de Microsoft y Google.

No se conectan a internet: comprueban que el código recorre bien las carpetas,
sigue la paginación y descarga o exporta cada archivo como corresponde.
"""
import json

import pytest
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence

import conector_google_drive
import conector_local
import conector_onedrive

GRAPH = conector_onedrive.GRAPH


# --------------------------------------------------------------------------- OneDrive
class RespuestaSimulada:
    def __init__(self, status=200, datos=None, contenido=b"", headers=None):
        self.status_code = status
        self._datos = datos or {}
        self._contenido = contenido
        self.headers = headers or {}

    def json(self):
        return self._datos

    def iter_content(self, chunk_size):
        yield self._contenido

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def graph_simulado(monkeypatch):
    """Simula un OneDrive con Documentos/Contratos (2 páginas) y una subcarpeta."""
    pagina_2 = f"{GRAPH}/me/drive/root:/Documentos/Contratos:/children?$skiptoken=abc"
    respuestas = {
        f"{GRAPH}/me/drive/root:/Documentos/Contratos:/children": RespuestaSimulada(datos={
            "value": [
                {"id": "A1", "name": "arriendo.pdf", "file": {}, "cTag": "c:1", "webUrl": "https://onedrive/arriendo"},
                {"id": "C1", "name": "2025", "folder": {"childCount": 1}},
            ],
            "@odata.nextLink": pagina_2,
        }),
        pagina_2: RespuestaSimulada(datos={
            "value": [{"id": "A2", "name": "servicios.docx", "file": {}, "eTag": "e:7"}],
        }),
        f"{GRAPH}/me/drive/items/C1/children": RespuestaSimulada(datos={
            "value": [{"id": "A3", "name": "anexo.txt", "file": {}, "lastModifiedDateTime": "2025-03-01T10:00:00Z"}],
        }),
        f"{GRAPH}/me/drive/items/A1/content": RespuestaSimulada(contenido=b"%PDF contenido"),
        f"{GRAPH}/me/drive/root:/No%20Existe:/children": RespuestaSimulada(status=404),
    }
    llamadas = []

    def get(url, headers=None, params=None, stream=False, timeout=None):
        llamadas.append({"url": url, "headers": headers, "params": params})
        return respuestas[url]

    monkeypatch.setattr(conector_onedrive.requests, "get", get)
    return llamadas


def test_onedrive_recorre_carpetas_y_paginas(graph_simulado):
    archivos = conector_onedrive.listar_archivos(["/Documentos/Contratos/"], obtener_token=lambda: "TOKEN")

    por_id = {a.id: a for a in archivos}
    assert set(por_id) == {"A1", "A2", "A3"}
    assert por_id["A1"].ruta == "OneDrive/Documentos/Contratos/arriendo.pdf"
    assert por_id["A3"].ruta == "OneDrive/Documentos/Contratos/2025/anexo.txt"
    # La versión usa cTag, luego eTag y por último la fecha de modificación
    assert [por_id[i].version for i in ("A1", "A2", "A3")] == ["c:1", "e:7", "2025-03-01T10:00:00Z"]
    assert por_id["A1"].url == "https://onedrive/arriendo"
    assert por_id["A2"].extension == ".docx"
    # Todas las peticiones llevan el token
    assert all(l["headers"] == {"Authorization": "Bearer TOKEN"} for l in graph_simulado)


def test_onedrive_descarga_el_contenido(graph_simulado, tmp_path):
    archivos = conector_onedrive.listar_archivos(["Documentos/Contratos"], obtener_token=lambda: "TOKEN")
    destino = tmp_path / "arriendo.pdf"

    next(a for a in archivos if a.id == "A1").descargar(destino)

    assert destino.read_bytes() == b"%PDF contenido"


def test_onedrive_carpeta_inexistente_da_un_mensaje_claro(graph_simulado):
    with pytest.raises(FileNotFoundError, match="No se encontró la carpeta 'No Existe'"):
        conector_onedrive.listar_archivos(["No Existe"], obtener_token=lambda: "TOKEN")


def test_onedrive_reintenta_cuando_microsoft_pide_esperar(monkeypatch):
    respuestas = iter([
        RespuestaSimulada(status=429, headers={"Retry-After": "0"}),
        RespuestaSimulada(datos={"value": []}),
    ])
    monkeypatch.setattr(conector_onedrive.requests, "get", lambda *a, **k: next(respuestas))
    monkeypatch.setattr(conector_onedrive.time, "sleep", lambda segundos: None)

    assert conector_onedrive.listar_archivos(["Docs"], obtener_token=lambda: "TOKEN") == []


def test_onedrive_exige_carpetas_configuradas():
    with pytest.raises(RuntimeError, match="ONEDRIVE_FOLDERS"):
        conector_onedrive.listar_archivos([], obtener_token=lambda: "TOKEN")


# ----------------------------------------------------------------------- Google Drive
def _ok(datos):
    return ({"status": "200"}, json.dumps(datos))


def test_google_drive_recorre_carpetas_y_exporta(tmp_path):
    carpeta = "application/vnd.google-apps.folder"
    http = HttpMockSequence([
        _ok({"name": "Proyectos"}),                                            # nombre de la carpeta raíz
        _ok({"files": [                                                         # contenido, página 1
            {"id": "P1", "name": "informe.pdf", "mimeType": "application/pdf",
             "md5Checksum": "abc", "webViewLink": "https://drive/informe"},
            {"id": "D1", "name": "Acta", "mimeType": "application/vnd.google-apps.document",
             "modifiedTime": "2025-05-01T00:00:00Z"},
        ], "nextPageToken": "pag2"}),
        _ok({"files": [                                                         # contenido, página 2
            {"id": "S1", "name": "Sub", "mimeType": carpeta},
            {"id": "F1", "name": "Encuesta", "mimeType": "application/vnd.google-apps.form"},
        ]}),
        _ok({"files": [                                                         # subcarpeta
            {"id": "H1", "name": "Presupuesto", "mimeType": "application/vnd.google-apps.spreadsheet",
             "modifiedTime": "2025-06-01T00:00:00Z"},
        ]}),
        ({"status": "200", "content-range": "bytes 0-11/12"}, b"%PDF informe"),  # descarga de P1
        ({"status": "200"}, b"Texto del acta"),                                  # exportación de D1
    ])
    servicio = build("drive", "v3", http=http, developerKey="clave-de-prueba")

    archivos = conector_google_drive.listar_archivos(
        ["https://drive.google.com/drive/folders/RAIZ123?usp=sharing"], servicio=servicio
    )

    por_id = {a.id: a for a in archivos}
    assert set(por_id) == {"P1", "D1", "F1", "H1"}
    assert por_id["P1"].ruta == "Google Drive/Proyectos/informe.pdf"
    assert por_id["H1"].ruta == "Google Drive/Proyectos/Sub/Presupuesto"
    # Los documentos de Google se guardan con la extensión del formato exportado
    assert [por_id[i].extension for i in ("P1", "D1", "H1", "F1")] == [".pdf", ".txt", ".csv", ".google"]
    assert por_id["P1"].version == "abc"
    assert por_id["D1"].version == "2025-05-01T00:00:00Z"

    por_id["P1"].descargar(tmp_path / "informe.pdf")
    por_id["D1"].descargar(tmp_path / "acta.txt")
    assert (tmp_path / "informe.pdf").read_bytes() == b"%PDF informe"
    assert (tmp_path / "acta.txt").read_bytes() == b"Texto del acta"


@pytest.mark.parametrize("valor, esperado", [
    ("1AbC_dEf-123", "1AbC_dEf-123"),
    ("https://drive.google.com/drive/folders/1AbC_dEf-123", "1AbC_dEf-123"),
    ("https://drive.google.com/drive/u/0/folders/1AbC_dEf-123?usp=drive_link", "1AbC_dEf-123"),
    ("https://drive.google.com/open?id=1AbC_dEf-123", "1AbC_dEf-123"),
])
def test_google_drive_acepta_id_o_enlace(valor, esperado):
    assert conector_google_drive.extraer_id(valor) == esperado


def test_google_drive_exige_carpetas_configuradas():
    with pytest.raises(RuntimeError, match="GDRIVE_FOLDERS"):
        conector_google_drive.listar_archivos([], servicio=object())


# ------------------------------------------------------------------------ Carpeta local
def test_local_lista_subcarpetas(carpeta_documentos):
    archivos = conector_local.listar_archivos([str(carpeta_documentos)])
    rutas = {a.ruta for a in archivos}
    assert "Empresa/Politicas/teletrabajo.md" in rutas
    assert "Empresa/contrato.pdf" in rutas


def test_local_carpeta_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        conector_local.listar_archivos([str(tmp_path / "no-existe")])
