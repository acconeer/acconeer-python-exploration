import attrs
import numpy as np


attrs_ndarray_eq = attrs.cmp_using(eq=np.array_equal)  # type: ignore[attr-defined]
