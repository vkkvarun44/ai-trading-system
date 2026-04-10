"""Market regime detection and regime-aware strategy parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator, MACD
from ta.volatility import AverageTrueRange

from core.logger import get_logger

logger = get_logger(__name__)

REGIME_TRENDING_UP = "TRENDING_UP"
REGIME_TRENDING_DOWN = "TRENDING_DOWN"
REGIME_SIDEWAYS = "SIDEWAYS"
REGIME_HIGH_VOLATILITY = "HIGH_VOLATILITY"

FEATURE_COLUMNS = [
    "rsi",
    "adx",
    "atr",
    "ema_50_slope",
    "ema_200_slope",
    "volatility",
    "volume_ratio",
    "trend_strength",
]


@dataclass(frozen=True, slots=True)
class StrategyParams:
    allowed_directions: tuple[str, ...]
    rsi_buy_threshold: float
    rsi_sell_threshold: float
    reward_ratio: float
    position_size_multiplier: float
    min_confidence: float = 0.6
    min_adx: float = 0.0


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    signal: str
    params: StrategyParams
    reason: str | None = None


def _series(df: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in df.columns:
            values = df[name]
            if isinstance(values, pd.DataFrame):
                values = values.iloc[:, 0]
            return pd.to_numeric(values, errors="coerce")
    raise KeyError(f"Missing required OHLCV column. Expected one of: {', '.join(names)}")


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add RSI, EMA50, EMA200, ADX, and ATR using the `ta` library."""

    result = df.copy()
    close = _series(result, "close", "Close")
    high = _series(result, "high", "High")
    low = _series(result, "low", "Low")

    result["rsi"] = RSIIndicator(close=close, window=14).rsi()
    result["ema_50"] = EMAIndicator(close=close, window=50).ema_indicator()
    result["ema_200"] = EMAIndicator(close=close, window=200).ema_indicator()
    result["adx"] = ADXIndicator(high=high, low=low, close=close, window=14).adx()
    result["atr"] = AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()
    macd = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
    result["macd"] = macd.macd()
    result["macd_signal"] = macd.macd_signal()
    return result


def create_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create model features and drop incomplete rows."""

    result = df.copy()
    close = _series(result, "close", "Close")
    volume = _series(result, "volume", "Volume")

    result["returns"] = close.pct_change(fill_method=None)
    result["ema_50_slope"] = result["ema_50"].pct_change(fill_method=None)
    result["ema_200_slope"] = result["ema_200"].pct_change(fill_method=None)
    result["volatility"] = result["returns"].rolling(window=20).std()
    result["volume_ratio"] = volume / volume.rolling(window=20).mean()
    result["trend_strength"] = result["ema_50"] - result["ema_200"]
    return result.dropna(subset=FEATURE_COLUMNS + ["returns"])


def label_market(df: pd.DataFrame) -> pd.DataFrame:
    """Label candles into market regimes for supervised training."""

    result = df.copy()
    close = _series(result, "close", "Close")
    rolling_volatility_mean = result["volatility"].rolling(window=20).mean()

    result["regime"] = REGIME_SIDEWAYS
    result.loc[(result["adx"] > 25) & (close > result["ema_50"]), "regime"] = REGIME_TRENDING_UP
    result.loc[(result["adx"] > 25) & (close <= result["ema_50"]), "regime"] = REGIME_TRENDING_DOWN
    result.loc[
        (result["adx"] <= 25) & (result["volatility"] > rolling_volatility_mean),
        "regime",
    ] = REGIME_HIGH_VOLATILITY
    return result.dropna(subset=FEATURE_COLUMNS + ["regime"])


def train_model(df: pd.DataFrame):
    """Train an XGBoost regime classifier with a time-series-safe split."""

    training_frame = df.dropna(subset=FEATURE_COLUMNS + ["regime"]).copy()
    if len(training_frame) < 50:
        raise ValueError("Insufficient regime training history. Need at least 50 labeled rows.")

    X = training_frame[FEATURE_COLUMNS]
    y = training_frame["regime"]
    if y.nunique() < 2:
        raise ValueError("Insufficient regime variety. Need at least two classes.")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        shuffle=False,
    )
    if y_train.nunique() < 2:
        raise ValueError("Training split has fewer than two regime classes.")

    label_encoder = LabelEncoder()
    y_train_encoded = label_encoder.fit_transform(y_train)
    known_test_mask = y_test.isin(label_encoder.classes_)
    X_eval = X_test.loc[known_test_mask]
    y_eval = label_encoder.transform(y_test.loc[known_test_mask]) if known_test_mask.any() else y_train_encoded
    X_eval = X_eval if known_test_mask.any() else X_train

    from xgboost import XGBClassifier

    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        objective="multi:softprob",
        num_class=len(label_encoder.classes_),
        eval_metric="mlogloss",
        min_child_weight=5,
        random_state=42,
        n_jobs=1,
        tree_method="hist",
    )
    model.fit(
        X_train,
        y_train_encoded,
        eval_set=[(X_eval, y_eval)],
        verbose=False,
    )
    model.regime_label_encoder = label_encoder

    predicted = model.predict(X_eval)
    accuracy = accuracy_score(y_eval, predicted)
    print(f"Market regime model accuracy: {accuracy:.4f}")
    print(
        classification_report(
            y_eval,
            predicted,
            labels=sorted(set(y_eval)),
            target_names=label_encoder.inverse_transform(sorted(set(y_eval))),
            zero_division=0,
        )
    )
    return model


def _feature_frame(row: pd.Series | dict[str, Any] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(row, pd.DataFrame):
        frame = row.tail(1).copy()
    elif isinstance(row, pd.Series):
        frame = row.to_frame().T
    else:
        frame = pd.DataFrame([row])
    return frame[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")


def predict_regime(model, latest_row: pd.Series | dict[str, Any] | pd.DataFrame) -> str:
    """Return the model-predicted regime for the latest candle."""

    prediction = model.predict(_feature_frame(latest_row))[0]
    label_encoder = getattr(model, "regime_label_encoder", None)
    if label_encoder is not None:
        return str(label_encoder.inverse_transform([int(prediction)])[0])
    return str(prediction)


def predict_with_confidence(model, row: pd.Series | dict[str, Any] | pd.DataFrame) -> tuple[str, float]:
    """Return regime prediction and model probability confidence."""

    features = _feature_frame(row)
    prediction = predict_regime(model, features)
    if not hasattr(model, "predict_proba"):
        return prediction, 1.0

    probabilities = model.predict_proba(features)[0]
    confidence = float(max(probabilities))
    return prediction, confidence


def get_strategy_params(regime: str) -> StrategyParams:
    """Return strategy parameters tuned to the detected market regime."""

    params = {
        REGIME_TRENDING_UP: StrategyParams(
            allowed_directions=("BUY",),
            rsi_buy_threshold=58.0,
            rsi_sell_threshold=42.0,
            reward_ratio=3.0,
            position_size_multiplier=1.0,
            min_adx=25.0,
        ),
        REGIME_TRENDING_DOWN: StrategyParams(
            allowed_directions=("SELL",),
            rsi_buy_threshold=58.0,
            rsi_sell_threshold=42.0,
            reward_ratio=3.0,
            position_size_multiplier=1.0,
            min_adx=25.0,
        ),
        REGIME_SIDEWAYS: StrategyParams(
            allowed_directions=("BUY", "SELL"),
            rsi_buy_threshold=65.0,
            rsi_sell_threshold=35.0,
            reward_ratio=1.5,
            position_size_multiplier=0.75,
        ),
        REGIME_HIGH_VOLATILITY: StrategyParams(
            allowed_directions=("BUY", "SELL"),
            rsi_buy_threshold=60.0,
            rsi_sell_threshold=40.0,
            reward_ratio=2.0,
            position_size_multiplier=0.5,
            min_confidence=0.65,
            min_adx=20.0,
        ),
    }
    return params.get(regime, params[REGIME_SIDEWAYS])


def evaluate_strategy_signal(
    *,
    row: pd.Series | dict[str, Any],
    regime: str,
    confidence: float,
) -> StrategyDecision:
    """Apply shared regime, confidence, direction, and momentum rules."""

    values = row if isinstance(row, dict) else row.to_dict()
    price = float(values.get("close", values.get("Close", values.get("price", 0.0))))
    ema_50 = float(values.get("ema_50", 0.0))
    ema_200 = float(values.get("ema_200", 0.0))
    rsi = float(values.get("rsi", 0.0))
    macd = float(values.get("macd", 0.0))
    macd_signal = float(values.get("macd_signal", 0.0))
    adx = float(values.get("adx", 0.0))
    volume_ratio = float(values.get("volume_ratio", 0.0))
    params = get_strategy_params(regime)

    if confidence < params.min_confidence:
        return StrategyDecision(
            "AVOID",
            params,
            f"Regime confidence {confidence:.2f} below {params.min_confidence:.2f}.",
        )
    if adx < params.min_adx and regime != REGIME_SIDEWAYS:
        return StrategyDecision(
            "AVOID",
            params,
            f"ADX {adx:.2f} below regime minimum {params.min_adx:.2f}.",
        )
    if volume_ratio <= 0:
        return StrategyDecision("AVOID", params, "Volume ratio is unavailable.")

    if regime == REGIME_TRENDING_UP:
        if price > ema_50 > ema_200 and rsi >= params.rsi_buy_threshold and macd > macd_signal:
            return StrategyDecision("BUY", params)
        return StrategyDecision("HOLD", params, "Trending-up setup lacks alignment or momentum.")

    if regime == REGIME_TRENDING_DOWN:
        if price < ema_50 < ema_200 and rsi <= params.rsi_sell_threshold and macd < macd_signal:
            return StrategyDecision("SELL", params)
        return StrategyDecision("HOLD", params, "Trending-down setup lacks alignment or momentum.")

    if regime == REGIME_HIGH_VOLATILITY:
        if price > ema_50 and "BUY" in params.allowed_directions and rsi >= params.rsi_buy_threshold:
            return StrategyDecision("BUY", params)
        if price < ema_50 and "SELL" in params.allowed_directions and rsi <= params.rsi_sell_threshold:
            return StrategyDecision("SELL", params)
        return StrategyDecision("HOLD", params, "High-volatility setup has no clear momentum edge.")

    if rsi <= params.rsi_sell_threshold and "BUY" in params.allowed_directions:
        return StrategyDecision("BUY", params)
    if rsi >= params.rsi_buy_threshold and "SELL" in params.allowed_directions:
        return StrategyDecision("SELL", params)
    return StrategyDecision("HOLD", params, "Sideways setup is not at a mean-reversion extreme.")


def calculate_atr_levels(
    *,
    price: float,
    atr: float,
    signal: str,
    params: StrategyParams,
    stop_multiplier: float = 1.5,
) -> tuple[float, float]:
    """Calculate ATR stop-loss and target using the regime reward ratio."""

    target_multiplier = stop_multiplier * params.reward_ratio
    if signal == "BUY":
        return price - (stop_multiplier * atr), price + (target_multiplier * atr)
    if signal == "SELL":
        return price + (stop_multiplier * atr), price - (target_multiplier * atr)
    return 0.0, 0.0


def rank_stocks(stock_data_dict: dict[str, pd.Series | dict[str, Any]], model) -> list[dict[str, Any]]:
    """Rank stocks by model confidence, trend strength, and volume strength."""

    ranked: list[dict[str, Any]] = []
    for symbol, row in stock_data_dict.items():
        regime, confidence = predict_with_confidence(model, row)
        values = row if isinstance(row, dict) else row.to_dict()
        trend_strength = abs(float(values.get("trend_strength", 0.0)))
        volume_ratio = float(values.get("volume_ratio", 0.0))
        score = (confidence * 0.5) + (trend_strength * 0.3) + (volume_ratio * 0.2)
        ranked.append(
            {
                "stock": symbol,
                "regime": regime,
                "confidence": confidence,
                "trend_strength": trend_strength,
                "volume_ratio": volume_ratio,
                "score": score,
                "features": row,
            }
        )

    return sorted(ranked, key=lambda item: item["score"], reverse=True)[:3]


def analyze_performance(trade_logs: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize trade feedback by regime for adaptive regime control."""

    if not trade_logs:
        return {
            "profit_by_regime": {},
            "win_rate_by_regime": {},
            "avg_profit_per_trade": 0.0,
            "weak_regimes": [],
            "disabled_regimes": [],
        }

    logs = pd.DataFrame(trade_logs)
    logs["profit"] = pd.to_numeric(logs["profit"], errors="coerce").fillna(0.0)
    grouped = logs.groupby("regime")["profit"]
    profit_by_regime = grouped.sum().to_dict()
    avg_profit_by_regime = grouped.mean().to_dict()
    win_rate_by_regime = grouped.apply(lambda profits: float((profits > 0).mean())).to_dict()
    weak_regimes = [
        regime
        for regime, avg_profit in avg_profit_by_regime.items()
        if avg_profit < 0 and win_rate_by_regime.get(regime, 0.0) < 0.45
    ]

    return {
        "profit_by_regime": profit_by_regime,
        "win_rate_by_regime": win_rate_by_regime,
        "avg_profit_per_trade": float(logs["profit"].mean()),
        "weak_regimes": weak_regimes,
        "disabled_regimes": weak_regimes,
    }


def prepare_regime_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Build a labeled regime frame from raw OHLCV candles."""

    return label_market(create_features(add_indicators(df)))


def detect_latest_regime(df: pd.DataFrame) -> tuple[str, float, pd.Series | None]:
    """Train on the supplied history and predict the latest market regime."""

    regime_frame = prepare_regime_frame(df)
    if regime_frame.empty:
        return REGIME_SIDEWAYS, 0.0, None

    latest_row = regime_frame.iloc[-1]
    try:
        model = train_model(regime_frame)
        regime, confidence = predict_with_confidence(model, latest_row)
        return regime, confidence, latest_row
    except Exception as exc:
        fallback_regime = str(latest_row.get("regime", REGIME_SIDEWAYS))
        logger.info(
            "Regime model fallback applied: %s. Using latest rule label %s.",
            exc,
            fallback_regime,
        )
        return fallback_regime, 0.0, latest_row
