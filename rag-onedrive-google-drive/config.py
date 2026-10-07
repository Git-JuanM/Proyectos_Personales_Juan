"""Configuración del sistema.

Todos los valores se leen del archivo .env (ver .env.example). Aquí no hay
ninguna credencial escrita: solo los nombres de las variables y sus valores
por defecto.
"""
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RAIZ = Path(__file__).resolve().parent


def _lista(valor):
    """Convierte 'a; b; c' en ['a', 'b', 'c'] (acepta ; o salto de línea)."""
    return [parte.strip() for parte in re.split(r"[;\n]", valor or "") if parte.strip()]


# --- IBM watsonx (modelo de lenguaje y embeddings) ---------------------------
WATSONX_APIKEY = os.getenv("WATSONX_APIKEY", "")
WATSONX_URL = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")

LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "ibm/granite-3-2-8b-instruct")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "512"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.5"))

# "watsonx" (como en el laboratorio) o "huggingface" (modelo local, sin API)
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "watsonx").lower()
EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID", "intfloat/multilingual-e5-large")
HF_EMBEDDING_MODEL = os.getenv(
    "HF_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
)

# --- Parámetros de RAG --------------------------------------------------------
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
TOP_K = int(os.getenv("TOP_K", "4"))

# Carpeta local donde se guardan las copias de los archivos y el índice
DATA_DIR = Path(os.getenv("DATA_DIR", str(RAIZ / "datos")))

# --- OneDrive -----------------------------------------------------------------
ONEDRIVE_CLIENT_ID = os.getenv("ONEDRIVE_CLIENT_ID", "")
ONEDRIVE_TENANT = os.getenv("ONEDRIVE_TENANT", "common")
ONEDRIVE_AUTH = os.getenv("ONEDRIVE_AUTH", "navegador").lower()   # "navegador" o "codigo"
ONEDRIVE_FOLDERS = _lista(os.getenv("ONEDRIVE_FOLDERS", ""))

# --- Google Drive ---------------------------------------------------------------
GDRIVE_CREDENTIALS_FILE = Path(os.getenv("GDRIVE_CREDENTIALS_FILE", str(RAIZ / "credentials.json")))
GDRIVE_FOLDERS = _lista(os.getenv("GDRIVE_FOLDERS", ""))

# --- Carpeta local (para probar sin configurar ninguna nube) -------------------
LOCAL_FOLDERS = _lista(os.getenv("LOCAL_FOLDERS", ""))
