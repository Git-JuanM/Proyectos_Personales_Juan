"""Piezas simuladas para probar el sistema sin internet ni credenciales.

- Embeddings simulados: convierten el texto en un vector contando palabras.
  No entienden significado, pero dos textos con las mismas palabras quedan
  cerca, que es suficiente para comprobar que la recuperación funciona.
- LLM simulado: devuelve siempre el mismo texto y guarda el prompt recibido.
"""
import hashlib
import math
import re
import sys
import zipfile
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.llms import LLM

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config      # noqa: E402
import rag_core    # noqa: E402


class EmbeddingsSimulados(Embeddings):
    DIMENSION = 256

    def _vector(self, texto):
        vector = [0.0] * self.DIMENSION
        for palabra in re.findall(r"\w+", texto.lower()):
            posicion = int(hashlib.md5(palabra.encode()).hexdigest(), 16) % self.DIMENSION
            vector[posicion] += 1.0
        norma = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norma for v in vector]

    def embed_documents(self, textos):
        return [self._vector(texto) for texto in textos]

    def embed_query(self, texto):
        return self._vector(texto)


class LLMSimulado(LLM):
    ultimo_prompt: str = ""

    @property
    def _llm_type(self):
        return "simulado"

    def _call(self, prompt, stop=None, run_manager=None, **kwargs):
        object.__setattr__(self, "ultimo_prompt", prompt)
        return " Respuesta simulada. "


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Carpeta de datos temporal y modelos simulados."""
    llm = LLMSimulado()
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "datos")
    monkeypatch.setattr(config, "TOP_K", 2)
    monkeypatch.setattr(rag_core, "embedding_model", lambda: EmbeddingsSimulados())
    monkeypatch.setattr(rag_core, "get_llm", lambda: llm)
    return llm


def crear_pdf(ruta, texto):
    """Escribe un PDF mínimo de una página con el texto dado."""
    contenido = f"BT /F1 12 Tf 72 720 Td ({texto}) Tj ET".encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(contenido)).encode() + b" >>\nstream\n" + contenido + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = b"%PDF-1.4\n"
    posiciones = []
    for numero, objeto in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += f"{numero} 0 obj\n".encode() + objeto + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for posicion in posiciones:
        salida += f"{posicion:010d} 00000 n \n".encode()
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n".encode()
    Path(ruta).write_bytes(salida)


def crear_docx(ruta, texto):
    """Escribe un documento de Word mínimo con un párrafo."""
    with zipfile.ZipFile(ruta, "w") as archivo:
        archivo.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        archivo.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        archivo.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{texto}</w:t></w:r></w:p></w:body></w:document>",
        )


@pytest.fixture
def carpeta_documentos(tmp_path):
    """Carpeta con un documento de cada tipo soportado y uno no soportado."""
    carpeta = tmp_path / "Empresa"
    (carpeta / "Politicas").mkdir(parents=True)

    (carpeta / "vacaciones.txt").write_text(
        "Política de vacaciones. Cada empleado tiene quince días hábiles de vacaciones al año.",
        encoding="utf-8",
    )
    (carpeta / "Politicas" / "teletrabajo.md").write_text(
        "# Teletrabajo\n\nSe permite el teletrabajo tres días por semana con aprobación del jefe.",
        encoding="utf-8",
    )
    (carpeta / "proveedores.csv").write_text(
        "proveedor,ciudad,contacto\nAcme,Bogotá,Laura\nGlobex,Medellín,Carlos\n", encoding="utf-8"
    )
    crear_pdf(carpeta / "contrato.pdf", "El contrato de arrendamiento vence el 31 de diciembre de 2027.")
    crear_docx(carpeta / "Politicas" / "viaticos.docx", "Los viaticos nacionales son de ciento veinte mil pesos diarios.")
    (carpeta / "foto.jpg").write_bytes(b"\xff\xd8\xff")
    (carpeta / "~$temporal.docx").write_bytes(b"x")
    return carpeta
