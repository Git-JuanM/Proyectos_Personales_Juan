"""
app_sin_modelo.py

Versión ligera de la API: es la que se desplegó en AWS (EC2 + RDS).

Qué hace este archivo:
- Crea una API con FastAPI para recibir datos de un cliente (telco churn).
- Se conecta a MySQL (en AWS, una base de datos de RDS).
- Crea (si no existe) la tabla `predictions` para guardar solicitudes y resultados.
- Expone un endpoint POST `/predict` que:
  - recibe un JSON con los datos del cliente,
  - calcula una predicción (aquí es un valor de ejemplo),
  - guarda el registro en MySQL,
  - devuelve `prediction` y `probability`.

Por qué existe: TensorFlow no se pudo instalar en la instancia EC2 de la capa
gratuita por falta de memoria. Esta versión no carga el modelo y sirvió para
probar en la nube el flujo completo API -> base de datos. La versión con el
modelo real está en app.py.

Cómo ejecutarlo (desde la carpeta api/):
    uvicorn app_sin_modelo:app --host 0.0.0.0 --port 8000
"""

# Para leer las credenciales desde variables de entorno.
import os

# Importa la clase principal de FastAPI (para crear la app y definir rutas).
from fastapi import FastAPI

# BaseModel sirve para validar/parsear automáticamente el JSON de entrada.
from pydantic import BaseModel

# Conector de MySQL para abrir conexiones, ejecutar SQL, etc.
import pymysql


# ----------------------------------------------------------------------------
# CREDENCIALES ELIMINADAS
# La versión original de este archivo tenía el host, el usuario y la contraseña
# de MySQL escritos directamente en el código. Se quitaron para no exponerlos
# en GitHub. Ahora la conexión se configura con variables de entorno:
#   DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
# En EC2 se definen con `export` (ver docs/03_despliegue_aws.md).
# ----------------------------------------------------------------------------

# Abre y devuelve una conexión nueva a MySQL con los datos de las variables de entorno.
def get_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME"),
        cursorclass=pymysql.cursors.DictCursor,
    )

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
# - calcula la predicción,
# - la guarda en MySQL,
# - devuelve el resultado.
@app.post("/predict")
def predict(data: CustomerData):

    probability = 0.65  # Probabilidad de churn (placeholder: aquí deberías usar tu modelo real).
    prediction = int(probability > 0.5)  # Convierte a 1/0 según umbral 0.5.

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
        data.gender,           # gender
        data.Partner,          # Partner
        data.Dependents,       # Dependents
        data.PhoneService,     # PhoneService
        data.MultipleLines,    # MultipleLines
        data.InternetService,  # InternetService
        data.OnlineSecurity,   # OnlineSecurity
        data.OnlineBackup,     # OnlineBackup
        data.DeviceProtection, # DeviceProtection
        data.TechSupport,      # TechSupport
        data.StreamingTV,      # StreamingTV
        data.StreamingMovies,  # StreamingMovies
        data.Contract,         # Contract
        data.PaperlessBilling, # PaperlessBilling
        data.PaymentMethod,    # PaymentMethod
        data.SeniorCitizen,    # SeniorCitizen
        data.tenure,           # tenure
        data.MonthlyCharges,   # MonthlyCharges
        data.TotalCharges,     # TotalCharges
        prediction,            # prediction calculada
        probability,           # probability calculada
    )

    cursor.execute(query, values)  # Ejecuta el INSERT con parámetros.
    conn.commit()                  # Confirma la transacción (guarda el registro).

    cursor.close()  # Cierra el cursor.
    conn.close()    # Cierra la conexión.

    # Respuesta JSON al cliente que llamó la API.
    return {
        "prediction": prediction,     # 0/1 según umbral.
        "probability": probability,   # Probabilidad (0..1).
    }
