import pandas as pd

from analysis.ml_model_v2 import MLTradingModelV2


def test_v2_balanced_sample_weight_upweights_minority_class():
    y = pd.Series([0, 0, 0, 0, 0, 0, 1, 1])

    weights = MLTradingModelV2._balanced_sample_weight(y)

    majority_weight = weights[y == 0][0]
    minority_weight = weights[y == 1][0]

    assert minority_weight > majority_weight
    assert round(minority_weight / majority_weight, 6) == 3.0
    assert len(weights) == len(y)
