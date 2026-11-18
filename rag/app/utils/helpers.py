import numpy as np


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(values))
    if norm == 0.0:
        return values
    return (values / norm).astype(np.float32, copy=False)


def l2_normalize_rows(matrix: np.ndarray) -> np.ndarray:
    values = np.asarray(matrix, dtype=np.float32)
    if values.size == 0:
        return values
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return (values / norms).astype(np.float32, copy=False)


def vector_to_blob(vector: np.ndarray) -> bytes:
    normalized = l2_normalize(vector)
    return normalized.astype("<f4", copy=False).tobytes()


def blob_to_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype="<f4").astype(np.float32, copy=True)
