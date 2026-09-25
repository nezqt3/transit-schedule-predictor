# Models

`torch_model.py` содержит компактную CPU-модель PyTorch для тех же признаков,
что используются в конкурсном CatBoost (`features_simple.py`). Она умеет
`fit`, `predict`, `save` и `load`; файл весов также хранит нормализацию.

`ensemble.py` объединяет residual CatBoost, direct CatBoost и PyTorch с
явным весом. На текущей временной проверке лучший вес PyTorch равен нулю,
поэтому CSV с ненулевым весом считается экспериментальным.
