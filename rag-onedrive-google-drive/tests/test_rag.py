"""Pruebas del núcleo RAG y de la sincronización, con modelos simulados."""
import pytest

import conector_local
import rag_core
from interfaz import crear_interfaz, formatear_fuentes
from sincronizar import carpeta_indice, sincronizar


def test_document_loader_lee_cada_tipo(carpeta_documentos):
    casos = {
        "vacaciones.txt": "quince días hábiles",
        "Politicas/teletrabajo.md": "tres días por semana",
        "proveedores.csv": "Medellín",
        "contrato.pdf": "31 de diciembre de 2027",
        "Politicas/viaticos.docx": "ciento veinte mil pesos",
    }
    for nombre, esperado in casos.items():
        documentos = rag_core.document_loader(carpeta_documentos / nombre)
        texto = " ".join(d.page_content for d in documentos)
        assert esperado in texto, nombre


def test_document_loader_rechaza_tipos_no_soportados(carpeta_documentos):
    with pytest.raises(ValueError):
        rag_core.document_loader(carpeta_documentos / "foto.jpg")


def test_text_splitter_respeta_el_tamano(carpeta_documentos, monkeypatch):
    monkeypatch.setattr(rag_core.config, "CHUNK_SIZE", 40)
    monkeypatch.setattr(rag_core.config, "CHUNK_OVERLAP", 10)
    chunks = rag_core.text_splitter(rag_core.document_loader(carpeta_documentos / "vacaciones.txt"))
    assert len(chunks) > 1
    assert all(len(chunk.page_content) <= 40 for chunk in chunks)


def test_sincronizar_indexa_y_detecta_cambios(entorno, carpeta_documentos):
    listar = lambda: conector_local.listar_archivos([str(carpeta_documentos)])

    # Primera vez: indexa los cinco documentos y omite la foto
    resumen = sincronizar("local", listar(), avisar=lambda _: None)
    assert len(resumen.indexados) == 5
    assert resumen.errores == []
    assert [motivo for _, motivo in resumen.omitidos] == ["tipo de archivo no soportado"]
    fragmentos_iniciales = resumen.fragmentos
    assert fragmentos_iniciales >= 5

    # Segunda vez sin cambios: no vuelve a indexar nada
    resumen = sincronizar("local", listar(), avisar=lambda _: None)
    assert len(resumen.indexados) == 0
    assert resumen.sin_cambios == 5
    assert resumen.fragmentos == fragmentos_iniciales

    # Se modifica un archivo: solo ese se vuelve a indexar, sin duplicar fragmentos
    (carpeta_documentos / "vacaciones.txt").write_text(
        "Política de vacaciones. Ahora son veinte días hábiles de vacaciones al año.", encoding="utf-8"
    )
    resumen = sincronizar("local", listar(), avisar=lambda _: None)
    assert resumen.indexados == ["Empresa/vacaciones.txt"]
    assert resumen.sin_cambios == 4
    assert resumen.fragmentos == fragmentos_iniciales

    # Se borra un archivo: sus fragmentos salen del índice
    (carpeta_documentos / "proveedores.csv").unlink()
    resumen = sincronizar("local", listar(), avisar=lambda _: None)
    assert resumen.eliminados == ["Empresa/proveedores.csv"]
    assert resumen.fragmentos < fragmentos_iniciales


def test_retriever_qa_usa_el_documento_correcto(entorno, carpeta_documentos):
    sincronizar("local", conector_local.listar_archivos([str(carpeta_documentos)]), avisar=lambda _: None)
    vectordb = rag_core.vector_database(carpeta_indice("local"))

    respuesta, documentos = rag_core.retriever_qa(vectordb, "¿Cuántos días de vacaciones tiene un empleado?")

    assert respuesta == "Respuesta simulada."
    assert documentos[0].metadata["source"] == "Empresa/vacaciones.txt"
    # El fragmento recuperado y la pregunta llegaron al modelo dentro del prompt
    assert "quince días hábiles" in entorno.ultimo_prompt
    assert "¿Cuántos días de vacaciones tiene un empleado?" in entorno.ultimo_prompt
    assert "no inventes una respuesta" in entorno.ultimo_prompt


def test_el_indice_se_conserva_en_disco(entorno, carpeta_documentos):
    resumen = sincronizar("local", conector_local.listar_archivos([str(carpeta_documentos)]), avisar=lambda _: None)

    vectordb = rag_core.vector_database(carpeta_indice("local"))    # Se abre de nuevo desde disco
    assert rag_core.cantidad_fragmentos(vectordb) == resumen.fragmentos


def test_cambiar_de_embeddings_exige_reindexar(entorno, carpeta_documentos, monkeypatch):
    listar = lambda: conector_local.listar_archivos([str(carpeta_documentos)])
    sincronizar("local", listar(), avisar=lambda _: None)

    monkeypatch.setattr(rag_core.config, "EMBEDDING_MODEL_ID", "otro-modelo")
    with pytest.raises(RuntimeError, match="--reindexar"):
        sincronizar("local", listar(), avisar=lambda _: None)


def test_un_archivo_danado_no_detiene_la_sincronizacion(entorno, carpeta_documentos):
    (carpeta_documentos / "roto.pdf").write_bytes(b"esto no es un pdf")
    resumen = sincronizar("local", conector_local.listar_archivos([str(carpeta_documentos)]), avisar=lambda _: None)

    assert len(resumen.indexados) == 5
    assert [ruta for ruta, _ in resumen.errores] == ["Empresa/roto.pdf"]


def test_interfaz_responde_con_fuentes(entorno, carpeta_documentos):
    sincronizar("local", conector_local.listar_archivos([str(carpeta_documentos)]), avisar=lambda _: None)
    aplicacion = crear_interfaz("local", "Prueba")

    respuesta, fuentes = aplicacion.fn("¿Cuándo vence el contrato de arrendamiento?")

    assert respuesta == "Respuesta simulada."
    assert "Empresa/contrato.pdf (página 1)" in fuentes


def test_interfaz_avisa_si_no_hay_documentos(entorno):
    aplicacion = crear_interfaz("local", "Prueba")
    respuesta, fuentes = aplicacion.fn("¿Hay algo?")
    assert "no hay documentos indexados" in respuesta
    assert fuentes == ""


def test_formatear_fuentes_no_repite_y_enlaza():
    from langchain_core.documents import Document
    documentos = [
        Document(page_content="a", metadata={"source": "OneDrive/a.pdf", "pagina": 2, "url": "https://ejemplo/a"}),
        Document(page_content="b", metadata={"source": "OneDrive/a.pdf", "pagina": 2, "url": "https://ejemplo/a"}),
        Document(page_content="c", metadata={"source": "OneDrive/b.txt"}),
    ]
    assert formatear_fuentes(documentos) == (
        "**Fuentes**\n\n- [OneDrive/a.pdf (página 2)](https://ejemplo/a)\n- OneDrive/b.txt"
    )
