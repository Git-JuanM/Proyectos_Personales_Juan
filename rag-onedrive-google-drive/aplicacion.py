"""Arranque común de las tres aplicaciones (OneDrive, Google Drive, local).

Pasos: 1) sincroniza las carpetas con el índice, 2) abre la interfaz web.
"""
import argparse

from interfaz import crear_interfaz
from sincronizar import borrar_indice, sincronizar


def ejecutar(fuente, titulo, listar_archivos, puerto):
    parser = argparse.ArgumentParser(description=titulo)
    parser.add_argument("--sin-sincronizar", action="store_true",
                        help="Abre la interfaz sin revisar si hay archivos nuevos.")
    parser.add_argument("--solo-sincronizar", action="store_true",
                        help="Actualiza el índice y termina, sin abrir la interfaz.")
    parser.add_argument("--reindexar", action="store_true",
                        help="Borra el índice y vuelve a indexar todo desde cero.")
    args = parser.parse_args()

    if args.reindexar:
        borrar_indice(fuente)

    if not args.sin_sincronizar:
        print("Revisando las carpetas configuradas...")
        resumen = sincronizar(fuente, listar_archivos())
        print(resumen)

    if not args.solo_sincronizar:
        rag_application = crear_interfaz(fuente, titulo)
        rag_application.launch(server_name="127.0.0.1", server_port=puerto)
