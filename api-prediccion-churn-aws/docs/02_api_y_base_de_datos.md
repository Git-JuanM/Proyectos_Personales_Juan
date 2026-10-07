# 2. API y base de datos

La API es el vehículo que conecta el modelo con la base de datos y con cualquier aplicación que quiera pedir una predicción. Está hecha con **FastAPI** y guarda cada predicción en **MySQL**.

El código está en la carpeta [`api/`](../api):

| Archivo | Qué hace | Dónde se usó |
|---|---|---|
| [`app.py`](../api/app.py) | API completa: carga el modelo, predice y guarda en MySQL | En local |
| [`app_sin_modelo.py`](../api/app_sin_modelo.py) | Misma API y misma tabla, pero devuelve una probabilidad fija en lugar de usar el modelo | En AWS (ver [despliegue](03_despliegue_aws.md)) |

Lo que sigue describe `app.py`.

## Conexión a la base de datos

> **Credenciales eliminadas.** La versión original tenía el usuario y la contraseña de MySQL escritos en el código. En este repositorio se leen de variables de entorno, de modo que ningún dato de acceso queda publicado.

```python
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)
```

Las variables se definen en un archivo `.env` (no se sube a GitHub). El archivo [`.env.example`](../.env.example) muestra cuáles son.

## Carga del modelo

Al iniciar, la API trae el modelo y los parámetros para preprocesar los datos de entrada:

```python
model = tf.keras.models.load_model(CARPETA_MODELO / "churn_model")
preprocessor = joblib.load(CARPETA_MODELO / "preprocessor.pkl")
```

## Tabla `predictions`

La función `create_table()` crea la tabla mediante SQL. El comando solo tiene efecto si la tabla todavía no existe en la base de datos.

```sql
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
```

Cada fila guarda los datos del cliente que se enviaron, el resultado de la predicción y la fecha.

La tabla se crea al arrancar la API, mediante un decorador que ejecuta la función cuando se inicia la aplicación:

```python
@app.on_event("startup")
def startup_event():
    create_table()
```

## Datos de entrada

La clase `CustomerData` le indica a la API qué variables debe recibir y de qué tipo. FastAPI la usa para validar cada petición: si falta un campo o el tipo no coincide, responde con un error sin llegar a ejecutar el modelo.

```python
class CustomerData(BaseModel):
    gender: str
    Partner: str
    Dependents: str
    PhoneService: str
    MultipleLines: str
    InternetService: str
    OnlineSecurity: str
    OnlineBackup: str
    DeviceProtection: str
    TechSupport: str
    StreamingTV: str
    StreamingMovies: str
    Contract: str
    PaperlessBilling: str
    PaymentMethod: str

    SeniorCitizen: int
    tenure: int
    MonthlyCharges: float
    TotalCharges: float
```

## Endpoint `POST /predict`

Es la función que se ejecuta cada vez que llega una petición:

1. Comprueba que los datos enviados concuerden con `CustomerData`.
2. Convierte los datos en un DataFrame y les aplica el preprocesador.
3. Calcula la probabilidad con el modelo y la convierte en 0 o 1 con un umbral de 0,5.
4. Guarda los datos de entrada y la predicción en MySQL.
5. Devuelve la predicción.

```python
@app.post("/predict")
def predict(data: CustomerData):
    input_df = pd.DataFrame([data.dict()])
    X_processed = preprocessor.transform(input_df)

    proba = model.predict(X_processed)[0][0]
    prediction = int(proba > 0.5)

    # ... INSERT en MySQL ...

    return {"prediction": prediction, "probability": float(proba)}
```

El `INSERT` usa una consulta parametrizada (`%s`): los valores se envían separados del texto SQL, lo que evita ataques de inyección SQL que podrían, por ejemplo, borrar la base de datos. El orden de las columnas en el `INSERT` debe coincidir con el orden de los valores.

## Cómo probarla

Con la API en ejecución, se entra a:

```
http://127.0.0.1:8000/docs
```

Es una dirección local: conecta con el propio computador y no es accesible desde internet. FastAPI genera ahí una página desde la que se pueden enviar peticiones.

1. Abrir `POST /predict` y pulsar **Try it out**.
2. Pegar un cliente de ejemplo:

```json
{
  "gender": "Male",
  "Partner": "Yes",
  "Dependents": "No",
  "PhoneService": "Yes",
  "MultipleLines": "No",
  "InternetService": "Fiber optic",
  "OnlineSecurity": "No",
  "OnlineBackup": "Yes",
  "DeviceProtection": "No",
  "TechSupport": "No",
  "StreamingTV": "Yes",
  "StreamingMovies": "Yes",
  "Contract": "Month-to-month",
  "PaperlessBilling": "Yes",
  "PaymentMethod": "Electronic check",
  "SeniorCitizen": 0,
  "tenure": 5,
  "MonthlyCharges": 89.85,
  "TotalCharges": 400.00
}
```

3. Pulsar **Execute**.

Respuesta del modelo para ese cliente:

```json
{
  "prediction": 1,
  "probability": 0.7710350155830383
}
```

El registro queda guardado en la tabla `predictions`.
