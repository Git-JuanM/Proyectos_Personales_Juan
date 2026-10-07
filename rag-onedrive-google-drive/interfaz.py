"""Interfaz web con Gradio, igual que en el laboratorio del curso."""
import gradio as gr

import rag_core
from sincronizar import carpeta_indice


def formatear_fuentes(documentos):
    """Lista sin repetir de los archivos de donde salió la respuesta."""
    lineas = []
    vistos = set()
    for documento in documentos:
        meta = documento.metadata
        clave = (meta.get("source"), meta.get("pagina"))
        if clave in vistos:
            continue
        vistos.add(clave)

        texto = meta.get("source", "Documento")
        if meta.get("pagina"):
            texto += f" (página {meta['pagina']})"
        if meta.get("url"):
            texto = f"[{texto}]({meta['url']})"
        lineas.append(f"- {texto}")
    if not lineas:
        return ""
    return "**Fuentes**\n\n" + "\n".join(lineas)


def crear_interfaz(fuente, titulo):
    vectordb = rag_core.vector_database(carpeta_indice(fuente))

    def responder(query):
        if not query or not query.strip():
            return "", ""
        if rag_core.cantidad_fragmentos(vectordb) == 0:
            return "Todavía no hay documentos indexados. Revisa las carpetas configuradas en .env.", ""

        respuesta, documentos = rag_core.retriever_qa(vectordb, query)
        return respuesta, formatear_fuentes(documentos)

    rag_application = gr.Interface(
        fn=responder,
        flagging_mode="never",
        inputs=gr.Textbox(
            label="Pregunta",
            lines=2,
            placeholder="Escribe tu pregunta aquí...",
        ),
        outputs=[
            gr.Textbox(label="Respuesta", lines=8),
            gr.Markdown(label="Fuentes"),
        ],
        title=titulo,
        description="Haz una pregunta y el asistente responderá con base en los documentos de las carpetas configuradas.",
        submit_btn="Preguntar",
        clear_btn="Limpiar",
        analytics_enabled=False,
    )

    return rag_application
