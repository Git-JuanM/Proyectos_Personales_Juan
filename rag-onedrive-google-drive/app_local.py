"""Asistente RAG sobre carpetas del computador (para probar sin configurar la nube).

Uso:  python app_local.py
"""
import conector_local
from aplicacion import ejecutar

if __name__ == "__main__":
    ejecutar(
        fuente=conector_local.FUENTE,
        titulo="Asistente de documentos (carpeta local)",
        listar_archivos=conector_local.listar_archivos,
        puerto=7862,
    )
