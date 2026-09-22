import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


class EnsureSPD(BaseEstimator, TransformerMixin):
    """
    Covariance matrix의 0 / 극소 / 음수 고유값을
    작은 양수로 보정하여 SPD를 보장한다.
    """

    def __init__(self, eps=1e-8):
        self.eps = eps

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X = np.asarray(X, dtype=np.float64)
        corrected = np.empty_like(X)

        for i, cov in enumerate(X):
            # 수치 오차로 인한 미세한 비대칭 제거
            cov = 0.5 * (cov + cov.T)

            eigvals, eigvecs = np.linalg.eigh(cov)

            # covariance 크기에 비례해서 최소 eigenvalue 결정
            scale = max(
                float(np.trace(cov) / cov.shape[0]),
                1e-12,
            )

            floor = self.eps * scale

            # 0 / 음수 / 지나치게 작은 eigenvalue 보정
            eigvals = np.maximum(
                eigvals,
                floor,
            )

            corrected[i] = (
                eigvecs
                @ np.diag(eigvals)
                @ eigvecs.T
            )

        return corrected