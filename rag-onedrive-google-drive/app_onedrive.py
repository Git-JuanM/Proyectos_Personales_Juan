"""Asistente RAG sobre carpetas de OneDrive.

Uso:  python app_onedrive.py
"""
import conector_onedrive
from aplicacion import ejecutar

if __name__ == "__main__":
    ejecutar(
        fuente=conector_onedrive.FUENTE,
        titulo="Asistente de documentos de OneDrive",
        listar_archivos=conector_onedrive.listar_archivos,
        puerto=7860,
    )
