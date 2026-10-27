# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

import argparse

import attrs
import numpy as np

from acconeer.exptool import a2
from acconeer.exptool.a2._core.channel_convention import get_tx_major_channel_indexes


def load_sub_results(path, tx_mask, rx_mask, subsampling_depths=1):
    """
    Loads subsampled results (use subsampling_depths=1 to skip subsampling data) using antenna masks.
    """

    # Assumes path is to a h5 record created with a2.H5Recorder such as barebones.py
    record = a2.open_record(path)

    session_config = record.session_config

    rx_record_mask = session_config.sensor_config.subsweep.rx_antenna_mask
    tx_record_mask = session_config.sensor_config.subsweep.tx_antenna_mask

    channels_record = get_tx_major_channel_indexes(tx_mask=tx_record_mask, rx_mask=rx_record_mask)
    channels_want = get_tx_major_channel_indexes(tx_mask=tx_mask, rx_mask=rx_mask)

    channel_index_to_extract = {
        k: channels_record[k]
        for k in channels_record.keys()
        if channels_record[k] in channels_want.values()
    }

    # Ensure that all data we want is present
    assert set(channels_want.values()).issubset(set(channels_record.values()))

    # Get shape of returned data
    num_channels_return = len(set(channels_want.keys()))
    num_distances = session_config.sensor_config.num_points
    num_distances_return = num_distances // subsampling_depths + int(
        num_distances % subsampling_depths > 0
    )
    ret_results = []

    # Go through all of the recorded data
    for group_result in record.group_results:
        result = group_result.result

        frame = result.get_subframe(session_config.sensor_config, 0, channel_index_to_extract)

        # Reshape the frame according to the channel masks and subsampling depths
        sub_frame = frame.reshape(
            (frame.shape[0], frame.shape[1] // num_channels_return, num_channels_return)
        )[:, ::subsampling_depths, :]
        frame = sub_frame.reshape((frame.shape[0], sub_frame.shape[1] * sub_frame.shape[2]))
        ret_result = attrs.evolve(result, frame=frame)
        ret_results.append(ret_result)

    results = np.array(ret_results)
    ret = {
        "results": results,
        "rx_mask": rx_mask,
        "tx_mask": tx_mask,
        "num_channels": num_channels_return,
        "num_distances": num_distances_return,
    }
    return ret


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file")
    parser.add_argument(
        "--rx-mask",
        default=0b101,
        type=lambda arg: int(arg, base=2),
        help="RX mask to use in binary format. For example: '1', '11' or '101'",
    )
    parser.add_argument(
        "--tx-mask",
        default=0b11,
        type=lambda arg: int(arg, base=2),
        help="TX mask to use in binary format. See RX mask doc.",
    )
    parser.add_argument(
        "--subsampling-depths",
        default=2,
        type=int,
        help="Subsample depths. Useful if one wants to subsample the depths (to simulate longer step lengths)",
    )

    args = parser.parse_args()

    filename = args.input_file
    rx_mask = args.rx_mask
    tx_mask = args.tx_mask
    subsampling_depths = args.subsampling_depths

    sub_results = load_sub_results(
        path=filename, tx_mask=tx_mask, rx_mask=rx_mask, subsampling_depths=subsampling_depths
    )

    print(sub_results["results"])


if __name__ == "__main__":
    main()
