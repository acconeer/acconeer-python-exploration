# Copyright (c) Acconeer AB, 2023
# All rights reserved

import itertools
import typing as t


def subsets_minus_empty_set(
    collection: t.Collection[t.Any],
) -> t.Iterator[t.Collection[t.Any]]:
    return itertools.chain.from_iterable(
        itertools.combinations(iterable=collection, r=subset_size)
        for subset_size in range(1, len(collection) + 1)
    )
