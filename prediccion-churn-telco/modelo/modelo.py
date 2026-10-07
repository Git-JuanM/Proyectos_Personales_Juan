"""Entrena el modelo final del proyecto y lo guarda en pipeline_churn.pkl.

El modelo es un Random Forest: fue el de mejor F1 y ROC-AUC en la comparación
de comparaciones/comparacion_modelos.ipynb, de donde salen sus hiperparámetros.

Uso:  python modelo.py
"""
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# Importa las clases desde transformadores.py, en vez de redefinirlas
from transformadores import LimpiarTotalCharges, EliminarColumnas, CrearCantidadServicios, MapearBinarias

CARPETA = Path(__file__).resolve().parent
RUTA_DATOS = CARPETA.parent / "data" / "telco_churn.csv"
RUTA_MODELO = CARPETA / "pipeline_churn.pkl"

# Carga y prepara datos
df = pd.read_csv(RUTA_DATOS)
df['Churn'] = df['Churn'].map({'No': 0, 'Yes': 1})
X = df.drop(columns=['Churn'])
y = df['Churn']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

# Arma el pipeline usando las clases importadas
columnas_servicios = ['OnlineBackup', 'DeviceProtection', 'StreamingTV', 'StreamingMovies']
binarias = ['Partner', 'Dependents', 'PaperlessBilling', 'OnlineSecurity', 'TechSupport']
nominales = ['InternetService', 'Contract', 'PaymentMethod']

preprocessor = ColumnTransformer(
    transformers=[('nominales', OneHotEncoder(drop='first', handle_unknown='ignore'), nominales)],
    remainder='passthrough'
)

pipeline_final = Pipeline([
    ('limpiar_totalcharges', LimpiarTotalCharges()),
    ('eliminar_columnas', EliminarColumnas(['gender', 'PhoneService', 'MultipleLines', 'customerID'])),
    ('crear_cantidad_servicios', CrearCantidadServicios(columnas_servicios)),
    ('mapear_binarias', MapearBinarias(binarias)),
    ('encoding_nominales', preprocessor),
    ('modelo', RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=5,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1,
    ))
])

# Entrena, evalúa en el conjunto de prueba y guarda
pipeline_final.fit(X_train, y_train)

pred = pipeline_final.predict(X_test)
proba = pipeline_final.predict_proba(X_test)[:, 1]
print(classification_report(y_test, pred, target_names=['No cancela', 'Cancela']))
print(f"ROC-AUC: {roc_auc_score(y_test, proba):.3f}")

joblib.dump(pipeline_final, RUTA_MODELO, compress=3)
print(f"Modelo entrenado y guardado en {RUTA_MODELO.name}")
