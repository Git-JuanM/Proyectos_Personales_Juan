"""Asistente RAG sobre carpetas de Google Drive.

Uso:  python app_google_drive.py
"""
import conector_google_drive
from aplicacion import ejecutar

if __name__ == "__main__":
    ejecutar(
        fuente=conector_google_drive.FUENTE,
        titulo="Asistente de documentos de Google Drive",
        listar_archivos=conector_google_drive.listar_archivos,
        puerto=7861,
    )
