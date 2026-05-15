import os
import numpy as np
import pickle

class BayesianLinear:
    """
    Implementa un modelo lineal con incertidumbre. 
    Permite el Thompson Sampling muestreando pesos de una distribución normal.
    """
    def __init__(self, dim, prior_var=5.0, noise_var=1.0):
        self.dim = dim
        self.noise_var = noise_var
        self.mu = np.zeros(dim)
        self.Sigma = np.eye(dim) * prior_var

    def sample_weights(self):
        return np.random.multivariate_normal(self.mu, self.Sigma)

    def update(self, x, y):
        # Actualización bayesiana recursiva para ajustar la media y covarianza
        x = x.reshape(-1, 1)
        Sigma_x = self.Sigma @ x
        gain = Sigma_x / (self.noise_var + x.T @ Sigma_x)

        self.mu = self.mu + (gain.flatten() * (y - self.mu @ x.flatten()))
        self.Sigma = self.Sigma - gain @ Sigma_x.T
    def save_model(self, filepath):
            """Guarda los parámetros del modelo en un archivo."""
            with open(filepath, 'wb') as f:
                pickle.dump({'mu': self.mu, 'Sigma': self.Sigma}, f)
    
    def load_model(self, filepath):
        """Carga los parámetros desde un archivo."""
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
                self.mu = data['mu']
                self.Sigma = data['Sigma']
            return True
        return False