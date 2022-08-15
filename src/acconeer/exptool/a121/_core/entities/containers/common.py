# Copyright (c) Acconeer AB, 2022
# All rights reserved

import attrs
import numpy as np


attrs_ndarray_eq = attrs.cmp_using(eq=np.array_equal)  # type: ignore[call-arg]
