# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations


def get_tx_major_channel_number(tx_idx: int, rx_idx: int) -> int:
    return tx_idx * 4 + rx_idx


def get_rx_major_channel_number(tx_idx: int, rx_idx: int) -> int:
    return rx_idx * 3 + tx_idx


def is_masked_in(tx_idx: int, rx_idx: int, tx_mask: int, rx_mask: int) -> int:
    tx_bit = 1 << tx_idx
    rx_bit = 1 << rx_idx
    return tx_bit & tx_mask and rx_bit & rx_mask


def get_tx_major_channel_numbers(tx_mask: int, rx_mask: int) -> dict[int, tuple[int, int]]:
    """Get Tx-major channel numbers and antenna indexes (tx, rx) given a pair of antenna masks

    >>> get_tx_major_channel_numbers(tx_mask=0b111, rx_mask=0b1111)
    {0:  (0, 0),
     1:  (0, 1),
     2:  (0, 2),
     3:  (0, 3),
     4:  (1, 0),
     5:  (1, 1),
     6:  (1, 2),
     7:  (1, 3),
     8:  (2, 0),
     9:  (2, 1),
     10: (2, 2),
     11: (2, 3)}

    >>> get_tx_major_channel_numbers(tx_mask=0b1, rx_mask=0b1)
    {0:  (0, 0)}
    """
    return {
        get_tx_major_channel_number(tx_idx, rx_idx): (tx_idx, rx_idx)
        for tx_idx in range(3)
        for rx_idx in range(4)
        if is_masked_in(tx_idx, rx_idx, tx_mask, rx_mask)
    }


def get_rx_major_channel_numbers(tx_mask: int, rx_mask: int) -> dict[int, tuple[int, int]]:
    """Get Rx-major channel numbers and antenna indexes (tx, rx) given a pair of antenna masks

    Note! The tuples of antenna indexes are still (tx_idx, rx_idx)

    >>> get_rx_major_channel_numbers(tx_mask=0b111, rx_mask=0b1111)
    {0:  (0, 0),
     1:  (1, 0),
     2:  (2, 0),
     3:  (0, 1),
     4:  (1, 1),
     5:  (2, 1),
     6:  (0, 2),
     7:  (1, 2),
     8:  (2, 2),
     9:  (0, 3),
     10: (1, 3),
     11: (2, 3)}

    >>> get_tx_major_channel_numbers(tx_mask=0b1, rx_mask=0b1)
    {0:  (0, 0)}
    """
    return {
        get_rx_major_channel_number(tx_idx, rx_idx): (tx_idx, rx_idx)
        for rx_idx in range(4)
        for tx_idx in range(3)
        if is_masked_in(tx_idx, rx_idx, tx_mask, rx_mask)
    }


def get_tx_major_channel_indexes(tx_mask: int, rx_mask: int) -> dict[int, tuple[int, int]]:
    """Get Tx-major channel numbers and antenna indexes (tx, rx) given a pair of antenna masks

    >>> get_tx_major_channel_indexes(tx_mask=0b1, rx_mask=0b1111)
    {0:  (0, 0),
     1:  (0, 1),
     2:  (0, 2),
     3:  (0, 3)}

    >>> get_tx_major_channel_indexes(tx_mask=0b10, rx_mask=0b1111)
    {0:  (1, 0),
     1:  (1, 1),
     2:  (1, 2),
     3:  (1, 3)}

    >>> get_tx_major_channel_indexes(tx_mask=0b100, rx_mask=0b1111)
    {0: (2, 0),
     1: (2, 1),
     2: (2, 2),
     3: (2, 3)}
    """
    channel_nbrs = get_tx_major_channel_numbers(tx_mask, rx_mask)
    return {
        channel_idx: tx_rx_tup for channel_idx, (_, tx_rx_tup) in enumerate(channel_nbrs.items())
    }


def get_rx_major_channel_indexes(tx_mask: int, rx_mask: int) -> dict[int, tuple[int, int]]:
    """Get Rx-major channel numbers and antenna indexes (tx, rx) given a pair of antenna masks

    Note! The tuples of antenna indexes are still (tx_idx, rx_idx)

    >>> get_rx_major_channel_indexes(tx_mask=0b111, rx_mask=0b1)
    {0: (0, 0),
     1: (1, 0),
     2: (2, 0)}

    >>> get_rx_major_channel_indexes(tx_mask=0b111, rx_mask=0b10)
    {0: (0, 1),
     1: (1, 1),
     2: (2, 1)}

    >>> get_rx_major_channel_indexes(tx_mask=0b111, rx_mask=0b100)
    {0: (0, 2),
     1: (1, 2),
     2: (2, 2)}

    >>> get_rx_major_channel_indexes(tx_mask=0b111, rx_mask=0b1000)
    {0: (0, 3),
     1: (1, 3),
     2: (2, 3)}
    """
    channel_nbrs = get_rx_major_channel_numbers(tx_mask, rx_mask)
    return {
        channel_idx: tx_rx_tup for channel_idx, (_, tx_rx_tup) in enumerate(channel_nbrs.items())
    }


def get_tx_major_to_rx_major_channel_index_table(tx_mask: int, rx_mask: int) -> dict[int, int]:
    """
    Get the Rx-major channel index, given a Tx-major channel index
    and the antenna masks.

    >>> get_tx_major_to_rx_major_channel_index_table(tx_mask=0b111, rx_mask=0b1111)
    {0: 0,
     1: 3,
     2: 6,
     3: 9,
     4: 1,
     5: 4,
     6: 7,
     7: 10,
     8: 2,
     9: 5,
     10: 8,
     11: 11}

    >>> get_tx_major_to_rx_major_channel_index_table(tx_mask=0b101, rx_mask=0b1111)
    {0: 0,
     1: 2,
     2: 4,
     3: 6,
     4: 1,
     5: 3,
     6: 5,
     7: 7}

    >>> get_tx_major_to_rx_major_channel_index_table(tx_mask=0b011, rx_mask=0b1111)
    {0: 0,
     1: 2,
     2: 4,
     3: 6,
     4: 1,
     5: 3,
     6: 5,
     7: 7}
    """
    tx_major_ch_idxs = get_tx_major_channel_indexes(tx_mask, rx_mask)
    rx_major_ch_idxs = get_rx_major_channel_indexes(tx_mask, rx_mask)

    return {
        tx_major_ch_idx: rx_major_ch_idx
        for tx_major_ch_idx, tx_major_antenna_idxs in tx_major_ch_idxs.items()
        for rx_major_ch_idx, rx_major_antenna_idxs in rx_major_ch_idxs.items()
        if tx_major_antenna_idxs == rx_major_antenna_idxs
    }


def get_subset_channel_indexes(
    tx_mask_super: int, rx_mask_super: int, tx_mask_sub: int, rx_mask_sub: int
) -> list[int]:
    """
    Given something channel_index-indexed, A, with masks tx_mask_super & rx_mask_super,
    we want a slice (B) of A with masks tx_mask_sub & rx_mask_sub.
    get_subset_channel_indexes(...) will provide the mapping from A to B.

    >>> get_subset_channel_indexes(
    ...     tx_mask_super=0b111,
    ...     rx_mask_super=0b1101,
    ...     tx_mask_sub=0b101,
    ...     rx_mask_sub=0b1001
    ... )
    [0, 2, 6, 8]
    """
    # ensure that the wanted channels is a subset of the present channels.
    assert tx_mask_super & tx_mask_sub == tx_mask_sub
    assert rx_mask_super & rx_mask_sub == rx_mask_sub

    channels_superset = get_tx_major_channel_indexes(tx_mask_super, rx_mask_super)
    channels_subset = get_tx_major_channel_numbers(tx_mask_sub, rx_mask_sub)
    inv_channels_superset = {v: k for k, v in channels_superset.items()}

    channel_indexes = [inv_channels_superset[value] for value in channels_subset.values()]
    channel_indexes.sort()  # Possibly redundant
    return channel_indexes
