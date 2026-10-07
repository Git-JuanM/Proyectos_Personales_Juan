"""Núcleo RAG.

Sigue la misma estructura del laboratorio del curso (qabot.py): una función por
etapa del flujo RAG.

    document_loader -> text_splitter -> embedding -> vector_database
                                                           |
                 pregunta -> retriever -> RetrievalQA (LLM) -> respuesta

Diferencias con el laboratorio:
- Carga varios tipos de archivo, no solo PDF.
- La base vectorial se guarda en disco, para no volver a calcular los
  embeddings en cada pregunta.
- Cada fragmento guarda de qué archivo salió, para poder citar la fuente.
"""
import warnings
from functools import lru_cache
from pathlib import Path

from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_community.vectorstores import Chroma

import config

warnings.filterwarnings("ignore", message=".*class `Chroma` was deprecated.*")

# Tipos de archivo que el sistema sabe leer
EXTENSIONES = {".pdf", ".txt", ".md", ".docx", ".csv"}

# Cuántos fragmentos se envían a la base vectorial en cada llamada
TAMANO_LOTE = 100


## LLM
@lru_cache(maxsize=1)
def get_llm():
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
    from langchain_ibm import WatsonxLLM

    _exigir_credenciales_watsonx()

    parameters = {
        GenParams.MAX_NEW_TOKENS: config.MAX_NEW_TOKENS,
        GenParams.TEMPERATURE: config.TEMPERATURE,
    }

    watsonx_llm = WatsonxLLM(
        model_id=config.LLM_MODEL_ID,
        url=config.WATSONX_URL,
        apikey=config.WATSONX_APIKEY,
        project_id=config.WATSONX_PROJECT_ID,
        params=parameters,
    )

    return watsonx_llm


## Document loader
def document_loader(ruta):
    """Lee un archivo y lo devuelve como lista de documentos de LangChain.

    Elige el cargador según la extensión del archivo.
    """
    ruta = Path(ruta)
    extension = ruta.suffix.lower()

    if extension == ".pdf":
        loader = PyPDFLoader(str(ruta))
    elif extension == ".docx":
        loader = Docx2txtLoader(str(ruta))
    elif extension == ".csv":
        return _cargar_texto(lambda codificacion: CSVLoader(file_path=str(ruta), encoding=codificacion))
    elif extension in (".txt", ".md"):
        return _cargar_texto(lambda codificacion: TextLoader(str(ruta), encoding=codificacion))
    else:
        raise ValueError(f"Tipo de archivo no soportado: {extension}")

    return loader.load()


def _cargar_texto(crear_loader):
    """Prueba UTF-8 y, si falla, la codificación habitual de Windows."""
    try:
        return crear_loader("utf-8").load()
    except Exception:
        return crear_loader("latin-1").load()


## Text splitter
def text_splitter(data):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        length_function=len,
    )
    chunks = text_splitter.split_documents(data)
    return chunks


## Embedding model
def watsonx_embedding():
    from langchain_ibm import WatsonxEmbeddings

    _exigir_credenciales_watsonx()

    embed_params = {
        "truncate_input_tokens": 512,
        "return_options": {
            "input_text": False
        },
    }

    watsonx_embedding = WatsonxEmbeddings(
        model_id=config.EMBEDDING_MODEL_ID,
        url=config.WATSONX_URL,
        apikey=config.WATSONX_APIKEY,
        project_id=config.WATSONX_PROJECT_ID,
        params=embed_params,
    )

    return watsonx_embedding


def huggingface_embedding():
    """Alternativa local (no usa la API de IBM). Requiere sentence-transformers."""
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        import sentence_transformers  # noqa: F401
    except ImportError as error:
        raise RuntimeError(
            "Para usar EMBEDDING_PROVIDER=huggingface instala: pip install sentence-transformers"
        ) from error

    return HuggingFaceEmbeddings(model_name=config.HF_EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def embedding_model():
    """Devuelve el modelo de embeddings configurado en .env."""
    if config.EMBEDDING_PROVIDER == "huggingface":
        return huggingface_embedding()
    return watsonx_embedding()


def nombre_embedding():
    """Identificador del modelo de embeddings en uso (se guarda junto al índice)."""
    if config.EMBEDDING_PROVIDER == "huggingface":
        return f"huggingface:{config.HF_EMBEDDING_MODEL}"
    return f"watsonx:{config.EMBEDDING_MODEL_ID}"


## Vector db
def vector_database(carpeta):
    """Abre (o crea) la base vectorial Chroma guardada en `carpeta`."""
    Path(carpeta).mkdir(parents=True, exist_ok=True)

    vectordb = Chroma(
        collection_name="documentos",
        embedding_function=embedding_model(),
        persist_directory=str(carpeta),
    )

    return vectordb


def indexar_archivo(vectordb, ruta, metadatos, id_archivo):
    """Carga un archivo, lo divide en fragmentos y los guarda en la base vectorial.

    Devuelve los ids de los fragmentos guardados, para poder borrarlos después
    si el archivo cambia o se elimina.
    """
    data = document_loader(ruta)
    chunks = text_splitter(data)
    chunks = [chunk for chunk in chunks if chunk.page_content.strip()]

    for chunk in chunks:
        pagina = chunk.metadata.get("page")
        chunk.metadata = dict(metadatos)
        if pagina is not None:
            chunk.metadata["pagina"] = int(pagina) + 1

    ids = [f"{id_archivo}:{i}" for i in range(len(chunks))]

    for inicio in range(0, len(chunks), TAMANO_LOTE):
        vectordb.add_documents(
            chunks[inicio:inicio + TAMANO_LOTE],
            ids=ids[inicio:inicio + TAMANO_LOTE],
        )

    return ids


def eliminar_fragmentos(vectordb, ids):
    """Borra de la base vectorial los fragmentos de un archivo."""
    for inicio in range(0, len(ids), TAMANO_LOTE):
        vectordb.delete(ids=ids[inicio:inicio + TAMANO_LOTE])


def cantidad_fragmentos(vectordb):
    return vectordb._collection.count()


## Retriever
def retriever(vectordb):
    retriever = vectordb.as_retriever(search_kwargs={"k": config.TOP_K})
    return retriever


## QA Chain
PROMPT_TEMPLATE = """Usa únicamente la información de los siguientes fragmentos de documentos para responder la pregunta del final. Si la respuesta no está en los fragmentos, di que no lo sabes; no inventes una respuesta. Responde en el mismo idioma de la pregunta.

{context}

Pregunta: {question}
Respuesta:"""

PROMPT = PromptTemplate(template=PROMPT_TEMPLATE, input_variables=["context", "question"])


def retriever_qa(vectordb, query):
    """Responde una pregunta con los documentos indexados.

    Devuelve la respuesta y la lista de fragmentos que se usaron como contexto.
    """
    llm = get_llm()
    retriever_obj = retriever(vectordb)

    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever_obj,
        chain_type_kwargs={"prompt": PROMPT},
        return_source_documents=True,
    )

    response = qa.invoke(query)

    return response["result"].strip(), response["source_documents"]


def _exigir_credenciales_watsonx():
    faltan = [
        nombre
        for nombre, valor in (
            ("WATSONX_APIKEY", config.WATSONX_APIKEY),
            ("WATSONX_PROJECT_ID", config.WATSONX_PROJECT_ID),
        )
        if not valor
    ]
    if faltan:
        raise RuntimeError(
            "Faltan variables en el archivo .env: " + ", ".join(faltan)
            + ". Copia .env.example como .env y complétalas."
        )
