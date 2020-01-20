import numpy as np
from keras.layers import (
    BatchNormalization,
    Conv1D,
    Conv2D,
    Dense,
    Dropout,
    Flatten,
    GaussianNoise,
    MaxPool2D,
)


def get_layers():
    layers = {
        "conv1d": {
            "class_str": "Conv1D",
            "class": Conv1D,
            "dimensions": 1,
            "params": {
                "filters": [32, int, [0, np.inf]],
                "kernel_size": [8, int, [1, np.inf]],
                "padding": ["drop_down", ["same", "None", "even"]],
                "activation": ["drop_down", ["relu"]],
            },
        },
        "conv2d": {
            "class_str": "Conv2D",
            "class": Conv2D,
            "dimensions": 2,
            "params": {
                "filters": [32, int, [0, np.inf]],
                "kernel_size": [(2, 2), int, [1, np.inf]],
                "strides": [(1, 1), int, [0, np.inf]],
                "padding": ["drop_down", ["same", "even", "None"]],
                "activation": ["drop_down", ["relu"]],
            },
        },
        "gaussian_noise": {
            "class_str": "GaussianNoise",
            "class": GaussianNoise,
            "dimensions": 0,
            "params": {
                "stddev": [0.3, float, [0, 1]],
            },
        },
        "batch_normalization": {
            "class_str": "BatchNormalization",
            "class": BatchNormalization,
            "dimensions": 0,
            "params": None,
        },
        "flatten": {
            "class_str": "Flatten",
            "class": Flatten,
            "dimensions": 0,
            "params": None,
        },
        "max_pooling2d": {
            "class_str": "MaxPool2D",
            "class": MaxPool2D,
            "dimensions": 2,
            "params": {
                "pool_size": [(2, 2), int, [1, np.inf]],
            },
        },
        "dropout": {
            "class_str": "Dropout",
            "class": Dropout,
            "dimensions": 0,
            "params": {
                "rate": [0.2, float, [0, 1]],
            },
        },
        "dense": {
            "class_str": "Dense",
            "class": Dense,
            "dimensions": 0,
            "params": {
                "units": [0, int, [0, np.inf]],
                "activation": ["drop_down", ["softmax"]],
            },
        },
    }

    return layers
