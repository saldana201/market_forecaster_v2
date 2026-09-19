"""Research-model registry and adapters for Market Forecaster 3.7.

The tournament layer is intentionally downstream of the 3.6 data/validation
contract. It provides model implementations only; it does not choose train/test
windows, targets, features, deployment status, or production champions.

Optional research dependencies:
- lightgbm
- catboost
- torch

If an optional dependency is not installed, the model is reported unavailable
and the rest of the tournament continues.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except ImportError:  # pragma: no cover
    XGBRegressor = None
    XGBOOST_AVAILABLE = False

try:
    from lightgbm import LGBMRegressor
    LIGHTGBM_AVAILABLE = True
except ImportError:  # pragma: no cover
    LGBMRegressor = None
    LIGHTGBM_AVAILABLE = False

try:
    from catboost import CatBoostRegressor
    CATBOOST_AVAILABLE = True
except ImportError:  # pragma: no cover
    CatBoostRegressor = None
    CATBOOST_AVAILABLE = False

try:
    import torch
    from torch import nn
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    torch = None
    nn = None
    F = None
    DataLoader = None
    TensorDataset = None
    TORCH_AVAILABLE = False


BASELINE_MODELS = ("zero_return", "historical_mean")
CORE_TABULAR_MODELS = (
    "ridge",
    "elastic_net",
    "random_forest",
    "hist_gradient_boosting",
    "xgboost",
)
OPTIONAL_TABULAR_MODELS = ("lightgbm", "catboost")
SEQUENCE_MODELS = ("lstm", "tcn", "transformer")
ALL_MODELS = BASELINE_MODELS + CORE_TABULAR_MODELS + OPTIONAL_TABULAR_MODELS + SEQUENCE_MODELS
DEFAULT_FAST_MODELS = BASELINE_MODELS + CORE_TABULAR_MODELS


@dataclass(frozen=True)
class ModelSpec:
    name: str
    family: str
    dependency: str
    available: bool
    sequence: bool
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


def model_registry() -> list[dict]:
    specs = [
        ModelSpec("zero_return", "baseline", "built-in", True, False, "Predicts zero future return / unchanged price."),
        ModelSpec("historical_mean", "baseline", "built-in", True, False, "Predicts the expanding-window mean target return."),
        ModelSpec("ridge", "linear", "scikit-learn", True, False, "L2-regularized linear regression."),
        ModelSpec("elastic_net", "linear", "scikit-learn", True, False, "Sparse L1/L2 regularized linear regression."),
        ModelSpec("random_forest", "tree", "scikit-learn", True, False, "Bagged nonlinear tree ensemble."),
        ModelSpec("hist_gradient_boosting", "boosting", "scikit-learn", True, False, "Histogram gradient boosting reference model."),
        ModelSpec("xgboost", "boosting", "xgboost", XGBOOST_AVAILABLE, False, "Current strong nonlinear benchmark."),
        ModelSpec("lightgbm", "boosting", "lightgbm", LIGHTGBM_AVAILABLE, False, "Leaf-wise gradient boosting challenger."),
        ModelSpec("catboost", "boosting", "catboost", CATBOOST_AVAILABLE, False, "Ordered boosting challenger."),
        ModelSpec("lstm", "deep_sequence", "torch", TORCH_AVAILABLE, True, "Causal LSTM over feature lookback windows."),
        ModelSpec("tcn", "deep_sequence", "torch", TORCH_AVAILABLE, True, "Causal temporal-convolution challenger."),
        ModelSpec("transformer", "deep_sequence", "torch", TORCH_AVAILABLE, True, "Compact Transformer encoder over causal lookback windows."),
    ]
    return [spec.to_dict() for spec in specs]


def model_status_map() -> dict[str, dict]:
    return {row["name"]: row for row in model_registry()}


def is_sequence_model(name: str) -> bool:
    return str(name).strip().lower() in SEQUENCE_MODELS


def is_model_available(name: str) -> bool:
    spec = model_status_map().get(str(name).strip().lower())
    return bool(spec and spec["available"])


def build_tabular_model(name: str, random_state: int):
    name = str(name).strip().lower()
    if name == "ridge":
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=3.0)),
        ])
    if name == "elastic_net":
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", ElasticNet(alpha=0.0005, l1_ratio=0.25, max_iter=5000, random_state=random_state)),
        ])
    if name == "random_forest":
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(
                n_estimators=250,
                max_depth=8,
                min_samples_leaf=5,
                max_features=0.75,
                n_jobs=1,
                random_state=random_state,
            )),
        ])
    if name == "hist_gradient_boosting":
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("model", HistGradientBoostingRegressor(
                loss="squared_error",
                learning_rate=0.05,
                max_iter=220,
                max_leaf_nodes=31,
                min_samples_leaf=20,
                l2_regularization=1.5,
                random_state=random_state,
            )),
        ])
    if name == "xgboost":
        if not XGBOOST_AVAILABLE:
            return None
        return XGBRegressor(
            objective="reg:squarederror",
            n_estimators=320,
            max_depth=4,
            learning_rate=0.035,
            min_child_weight=5,
            subsample=0.82,
            colsample_bytree=0.82,
            reg_alpha=0.05,
            reg_lambda=2.0,
            tree_method="hist",
            n_jobs=1,
            random_state=random_state,
            verbosity=0,
        )
    if name == "lightgbm":
        if not LIGHTGBM_AVAILABLE:
            return None
        return LGBMRegressor(
            objective="regression_l1",
            n_estimators=320,
            learning_rate=0.03,
            num_leaves=24,
            max_depth=-1,
            min_child_samples=20,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.05,
            reg_lambda=1.5,
            random_state=random_state,
            n_jobs=1,
            verbosity=-1,
        )
    if name == "catboost":
        if not CATBOOST_AVAILABLE:
            return None
        return CatBoostRegressor(
            loss_function="MAE",
            iterations=320,
            depth=6,
            learning_rate=0.035,
            l2_leaf_reg=4.0,
            random_seed=random_state,
            verbose=False,
            allow_writing_files=False,
            thread_count=1,
        )
    return None


def _seed_everything(seed: int) -> None:
    np.random.seed(seed)
    if not TORCH_AVAILABLE:
        return
    torch.manual_seed(seed)
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception:
        pass
    try:
        torch.set_num_threads(1)
    except Exception:
        pass


def _prepare_scaled_matrix(
    X: pd.DataFrame,
    train_start: int,
    train_end: int,
) -> np.ndarray:
    """Fit imputation/scaling only on the training portion; transform all rows."""
    train = X.iloc[train_start:train_end]
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    train_imp = imputer.fit_transform(train)
    scaler.fit(train_imp)
    all_imp = imputer.transform(X)
    return scaler.transform(all_imp).astype("float32")


def _sequence_tensor(
    matrix: np.ndarray,
    indices: np.ndarray,
    lookback: int,
) -> tuple[np.ndarray, np.ndarray]:
    seqs: list[np.ndarray] = []
    kept: list[int] = []
    for idx in indices:
        start = int(idx) - int(lookback) + 1
        if start < 0:
            continue
        seqs.append(matrix[start:int(idx) + 1])
        kept.append(int(idx))
    if not seqs:
        return np.empty((0, lookback, matrix.shape[1]), dtype="float32"), np.empty((0,), dtype=int)
    return np.stack(seqs).astype("float32"), np.asarray(kept, dtype=int)


if TORCH_AVAILABLE:
    class _LSTMRegressor(nn.Module):
        def __init__(self, features: int, hidden: int = 32):
            super().__init__()
            self.lstm = nn.LSTM(features, hidden, num_layers=1, batch_first=True)
            self.head = nn.Sequential(nn.LayerNorm(hidden), nn.Linear(hidden, 1))

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1, :]).squeeze(-1)


    class _TCNRegressor(nn.Module):
        def __init__(self, features: int, hidden: int = 32):
            super().__init__()
            self.conv1 = nn.Conv1d(features, hidden, kernel_size=3, padding=0, dilation=1)
            self.conv2 = nn.Conv1d(hidden, hidden, kernel_size=3, padding=0, dilation=2)
            self.head = nn.Sequential(nn.LayerNorm(hidden), nn.Linear(hidden, 1))

        def forward(self, x):
            # Left-only padding makes both convolutions strictly causal.
            z = x.transpose(1, 2)
            z = self.conv1(F.pad(z, (2, 0)))
            z = F.gelu(z)
            z = self.conv2(F.pad(z, (4, 0)))
            z = F.gelu(z)
            return self.head(z[:, :, -1]).squeeze(-1)


    class _TransformerRegressor(nn.Module):
        def __init__(self, features: int, lookback: int, d_model: int = 32):
            super().__init__()
            self.input_proj = nn.Linear(features, d_model)
            self.position = nn.Parameter(torch.zeros(1, lookback, d_model))
            layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=4,
                dim_feedforward=64,
                dropout=0.0,
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=2)
            self.head = nn.Sequential(nn.LayerNorm(d_model), nn.Linear(d_model, 1))

        def forward(self, x):
            z = self.input_proj(x) + self.position[:, : x.shape[1], :]
            z = self.encoder(z)
            return self.head(z[:, -1, :]).squeeze(-1)


def _make_deep_model(name: str, features: int, lookback: int):
    if not TORCH_AVAILABLE:
        return None
    if name == "lstm":
        return _LSTMRegressor(features)
    if name == "tcn":
        return _TCNRegressor(features)
    if name == "transformer":
        return _TransformerRegressor(features, lookback)
    return None


def fit_predict_sequence(
    name: str,
    X: pd.DataFrame,
    y: pd.Series,
    *,
    train_start: int,
    train_end: int,
    test_start: int,
    test_end: int,
    lookback: int = 20,
    epochs: int = 15,
    batch_size: int = 64,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit a causal sequence model and predict the requested test target rows.

    Returns `(predictions, kept_test_indices)`. The scaler/imputer is fitted only
    on the training rows. Test sequences may use feature context from prior test
    origins because those features are observable by the later forecast origin;
    no test targets are used during fitting.
    """
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch is not installed")
    name = str(name).strip().lower()
    if name not in SEQUENCE_MODELS:
        raise ValueError(f"Unknown sequence model: {name}")

    lookback = max(5, int(lookback))
    epochs = max(1, int(epochs))
    batch_size = max(8, int(batch_size))
    _seed_everything(int(random_state))

    matrix = _prepare_scaled_matrix(X, train_start, train_end)
    train_indices = np.arange(train_start, train_end, dtype=int)
    test_indices = np.arange(test_start, test_end, dtype=int)
    train_seq, kept_train = _sequence_tensor(matrix, train_indices, lookback)
    test_seq, kept_test = _sequence_tensor(matrix, test_indices, lookback)
    if len(train_seq) < 40 or len(test_seq) == 0:
        raise RuntimeError("Not enough causal sequence samples for deep model")

    y_values = pd.to_numeric(y, errors="coerce").to_numpy(dtype="float32")
    train_y = y_values[kept_train]
    good_train = np.isfinite(train_y)
    train_seq = train_seq[good_train]
    train_y = train_y[good_train]
    if len(train_seq) < 40:
        raise RuntimeError("Not enough finite training targets for deep model")

    # Standardize the small-magnitude return target using training data only.
    # This materially improves neural optimization without leaking test labels.
    target_mean = float(np.mean(train_y))
    target_std = float(np.std(train_y))
    if not np.isfinite(target_std) or target_std < 1e-6:
        target_std = 1.0
    train_y_scaled = ((train_y - target_mean) / target_std).astype("float32")

    train_ds = TensorDataset(
        torch.from_numpy(train_seq),
        torch.from_numpy(train_y_scaled),
    )
    generator = torch.Generator().manual_seed(int(random_state))
    loader = DataLoader(
        train_ds,
        batch_size=min(batch_size, len(train_ds)),
        shuffle=True,
        generator=generator,
    )

    model = _make_deep_model(name, matrix.shape[1], lookback)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.SmoothL1Loss(beta=1.0)
    model.train()
    for _ in range(epochs):
        for xb, yb in loader:
            optimizer.zero_grad(set_to_none=True)
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

    model.eval()
    with torch.no_grad():
        pred_scaled = model(torch.from_numpy(test_seq)).cpu().numpy().astype(float)
    pred = pred_scaled * target_std + target_mean
    return pred, kept_test
