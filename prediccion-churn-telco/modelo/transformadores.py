# transformadores.py
from sklearn.base import BaseEstimator, TransformerMixin
import pandas as pd

class LimpiarTotalCharges(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self
    def transform(self, X):
        X = X.copy()
        X['TotalCharges'] = pd.to_numeric(X['TotalCharges'], errors='coerce')
        X['TotalCharges'] = X['TotalCharges'].fillna(0)
        return X

class EliminarColumnas(BaseEstimator, TransformerMixin):
    def __init__(self, columnas_a_eliminar):
        self.columnas_a_eliminar = columnas_a_eliminar
    def fit(self, X, y=None):
        return self
    def transform(self, X):
        X = X.copy()
        return X.drop(columns=self.columnas_a_eliminar, errors='ignore')

class CrearCantidadServicios(BaseEstimator, TransformerMixin):
    def __init__(self, columnas_servicios):
        self.columnas_servicios = columnas_servicios
    def fit(self, X, y=None):
        return self
    def transform(self, X):
        X = X.copy()
        X['cantidad_servicios'] = (X[self.columnas_servicios] == 'Yes').sum(axis=1)
        return X.drop(columns=self.columnas_servicios)

class MapearBinarias(BaseEstimator, TransformerMixin):
    def __init__(self, columnas_binarias):
        self.columnas_binarias = columnas_binarias
    def fit(self, X, y=None):
        return self
    def transform(self, X):
        X = X.copy()
        mapeo = {'No': 0, 'Yes': 1, 'No internet service': 0}
        for col in self.columnas_binarias:
            X[col] = X[col].map(mapeo)
        return X