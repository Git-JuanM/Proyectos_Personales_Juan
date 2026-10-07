"""
app.py

API completa de predicción de churn.

Qué hace este archivo:
- Crea una API con FastAPI para recibir los datos de un cliente de telecomunicaciones.
- Carga el modelo de Keras y el preprocesador entrenados en notebooks/entrenamiento_modelo.ipynb.
- Se conecta a MySQL y crea (si no existe) la tabla `predictions`.
- Expone un endpoint POST `/predict` que:
  - recibe un JSON con los datos del cliente,
  - aplica el preprocesador y calcula la predicción con el modelo,
  - guarda los datos y el resultado en MySQL,
  - devuelve `prediction` y `probability`.

Cómo ejecutarlo (desde la carpeta api/):
    uvicorn app:app --reload
"""

# Para leer las credenciales desde variables de entorno y ubicar los archivos del modelo.
import os
from pathlib import Path

# Importa la clase principal de FastAPI (para crear la app y definir rutas).
from fastapi import FastAPI

# BaseModel sirve para validar/parsear automáticamente el JSON de entrada.
from pydantic import BaseModel

# Conector de MySQL para abrir conexiones, ejecutar SQL, etc.
import mysql.connector

import pandas as pd
import joblib
import tensorflow as tf

# Carga las variables definidas en un archivo .env, si existe (ver .env.example).
from dotenv import load_dotenv

load_dotenv()

# ----------------------------------------------------------------------------
# CREDENCIALES ELIMINADAS
# La versión original de este archivo tenía el usuario y la contraseña de MySQL
# escritos directamente en el código. Se quitaron para no exponerlos en GitHub.
# Ahora la conexión se configura con variables de entorno:
#   DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
# Copia .env.example como .env y completa tus propios valores.
# ----------------------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),   # Host donde corre MySQL (localhost si está en tu PC).
    "port": int(os.getenv("DB_PORT", "3306")),   # Puerto de MySQL.
    "user": os.getenv("DB_USER"),                # Usuario de MySQL.
    "password": os.getenv("DB_PASSWORD"),        # Contraseña del usuario.
    "database": os.getenv("DB_NAME"),            # Nombre de la base de datos (debe existir).
}

# Rutas del modelo y del preprocesador (carpeta modelo/ del repositorio).
CARPETA_MODELO = Path(__file__).resolve().parent.parent / "modelo"

# Se trae el modelo y los parámetros para preprocesar los datos de entrada.
model = tf.keras.models.load_model(CARPETA_MODELO / "churn_model")
preprocessor = joblib.load(CARPETA_MODELO / "preprocessor.pkl")


# Abre y devuelve una conexión nueva a MySQL usando DB_CONFIG.
def get_connection():
    return mysql.connector.connect(**DB_CONFIG)  # **DB_CONFIG expande el dict en argumentos keyword.


# Crea la tabla `predictions` si todavía no existe.
def create_table():
    conn = get_connection()     # Abre conexión a MySQL.
    cursor = conn.cursor()      # Crea un cursor para ejecutar SQL.

    # Ejecuta un CREATE TABLE (si no existe) para guardar:
    # - features del cliente (columnas tipo texto y numéricas),
    # - resultado de predicción (prediction/probability),
    # - timestamp de creación.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            id INT AUTO_INCREMENT PRIMARY KEY,

            gender VARCHAR(10),
            Partner VARCHAR(5),
            Dependents VARCHAR(5),
            PhoneService VARCHAR(5),
            MultipleLines VARCHAR(20),
            InternetService VARCHAR(20),
            OnlineSecurity VARCHAR(20),
            OnlineBackup VARCHAR(20),
            DeviceProtection VARCHAR(20),
            TechSupport VARCHAR(20),
            StreamingTV VARCHAR(20),
            StreamingMovies VARCHAR(20),
            Contract VARCHAR(20),
            PaperlessBilling VARCHAR(5),
            PaymentMethod VARCHAR(50),

            SeniorCitizen INT,
            tenure INT,
            MonthlyCharges FLOAT,
            TotalCharges FLOAT,

            prediction INT,
            probability FLOAT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()        # Guarda (confirma) los cambios (DDL) en la BD.
    cursor.close()       # Cierra el cursor.
    conn.close()         # Cierra la conexión.


# Modelo de entrada: describe el JSON esperado en el POST /predict.
# FastAPI usará este modelo para validar tipos y generar documentación (Swagger).
class CustomerData(BaseModel):
    gender: str  # Género (por ejemplo: "Male", "Female").
    Partner: str  # Si tiene pareja (p.ej. "Yes"/"No").
    Dependents: str  # Si tiene dependientes (p.ej. "Yes"/"No").
    PhoneService: str  # Tiene servicio telefónico (p.ej. "Yes"/"No").
    MultipleLines: str  # Múltiples líneas (p.ej. "Yes"/"No"/"No phone service").
    InternetService: str  # Tipo de internet (p.ej. "DSL", "Fiber optic", "No").
    OnlineSecurity: str  # Seguridad online (p.ej. "Yes"/"No").
    OnlineBackup: str  # Backup online (p.ej. "Yes"/"No").
    DeviceProtection: str  # Protección de dispositivo (p.ej. "Yes"/"No").
    TechSupport: str  # Soporte técnico (p.ej. "Yes"/"No").
    StreamingTV: str  # Streaming TV (p.ej. "Yes"/"No").
    StreamingMovies: str  # Streaming películas (p.ej. "Yes"/"No").
    Contract: str  # Tipo de contrato (p.ej. "Month-to-month", "One year", "Two year").
    PaperlessBilling: str  # Facturación sin papel (p.ej. "Yes"/"No").
    PaymentMethod: str  # Método de pago (p.ej. "Electronic check", etc.).

    SeniorCitizen: int  # 1 si es adulto mayor, 0 si no.
    tenure: int  # Antigüedad (meses) con la compañía.
    MonthlyCharges: float  # Cargo mensual.
    TotalCharges: float  # Cargo total acumulado.


# Crea la aplicación FastAPI y define el título que verás en /docs.
app = FastAPI(title="Telco Churn Prediction API")


# Evento que corre al iniciar la app (antes de atender requests).
# Aquí se asegura que la tabla exista.
@app.on_event("startup")
def startup_event():
    create_table()  # Crea la tabla si no existe.


# Endpoint POST /predict:
# - recibe `data` como CustomerData (validado por Pydantic),
# - calcula la predicción con el modelo,
# - la guarda en MySQL,
# - devuelve el resultado.
@app.post("/predict")
def predict(data: CustomerData):

    # 1. Convertir la entrada en DataFrame (una fila, con los nombres de columna del entrenamiento).
    input_df = pd.DataFrame([data.dict()])

    # 2. Aplicar el preprocesador (escalado y one-hot aprendidos en el entrenamiento).
    X_processed = preprocessor.transform(input_df)

    # 3. Predicción con el modelo.
    proba = model.predict(X_processed)[0][0]   # Probabilidad de churn (0..1).
    prediction = int(proba > 0.5)              # Convierte a 1/0 según umbral 0.5.

    # 4. Guardar en MySQL.
    conn = get_connection()  # Abre conexión a MySQL.
    cursor = conn.cursor()   # Crea cursor para ejecutar el INSERT.

    # SQL parametrizado (evita SQL injection y maneja correctamente tipos).
    # IMPORTANTE: el orden de columnas debe coincidir con el orden de `values`.
    query = """
        INSERT INTO predictions (
            gender, Partner, Dependents, PhoneService, MultipleLines,
            InternetService, OnlineSecurity, OnlineBackup, DeviceProtection,
            TechSupport, StreamingTV, StreamingMovies, Contract,
            PaperlessBilling, PaymentMethod,
            SeniorCitizen, tenure, MonthlyCharges, TotalCharges,
            prediction, probability
        )
        VALUES (%s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s)
    """

    # Tupla de valores en el mismo orden del INSERT.
    values = (
        data.gender,
        data.Partner,
        data.Dependents,
        data.PhoneService,
        data.MultipleLines,
        data.InternetService,
        data.OnlineSecurity,
        data.OnlineBackup,
        data.DeviceProtection,
        data.TechSupport,
        data.StreamingTV,
        data.StreamingMovies,
        data.Contract,
        data.PaperlessBilling,
        data.PaymentMethod,
        data.SeniorCitizen,
        data.tenure,
        data.MonthlyCharges,
        data.TotalCharges,
        prediction,
        float(proba),
    )

    cursor.execute(query, values)  # Ejecuta el INSERT con parámetros.
    conn.commit()                  # Confirma la transacción (guarda el registro).

    cursor.close()  # Cierra el cursor.
    conn.close()    # Cierra la conexión.

    # 5. Respuesta JSON al cliente que llamó la API.
    return {
        "prediction": prediction,     # 0/1 según umbral.
        "probability": float(proba),  # Probabilidad (0..1).
    }
