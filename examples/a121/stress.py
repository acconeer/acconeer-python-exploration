# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import time
import typing as t

import acconeer.exptool as et
from acconeer.exptool import a121


def main() -> None:
    parser = a121.ExampleArgumentParser()

    parser.add_argument(
        "program",
        choices=[
            "throughput",
            "rate",
            "short_pauses",
            "long_pauses",
            "flow",
        ],
    )

    args = parser.parse_args()
    et.utils.config_logging(args)

    client = a121.Client(**a121.get_client_args(args))
    client.connect()
    print(client.client_info)
    print()
    print(client.server_info)
    print()

    if args.program == "throughput":
        func = throughput
    elif args.program == "rate":
        func = rate
    elif args.program == "short_pauses":
        func = short_pauses
    elif args.program == "long_pauses":
        func = long_pauses
    elif args.program == "flow":
        func = flow
    else:
        raise RuntimeError

    try:
        func(client)
    except KeyboardInterrupt:
        print()
        try:
            client.disconnect()
        except Exception:
            pass


def flow(client: a121.Client) -> None:
    client.disconnect()

    n = 0

    while True:
        client.connect()

        for _ in range(5):
            client.setup_session(a121.SensorConfig())
            client.start_session()

            for _ in range(5):
                client.get_next()

            client.stop_session()

        client.disconnect()

        n += 1

        print_status(f"{n:8}")


def throughput(client: a121.Client) -> None:
    config = a121.SensorConfig(
        hwaas=1,
        profile=a121.Profile.PROFILE_5,
        prf=a121.PRF.PRF_13_0_MHz,
        sweeps_per_frame=1,
        start_point=0,
        num_points=2047,
        step_length=1,
        double_buffering=True,
    )
    _stress_session(client, config)


def rate(client: a121.Client) -> None:
    config = a121.SensorConfig(
        hwaas=1,
        profile=a121.Profile.PROFILE_5,
        prf=a121.PRF.PRF_13_0_MHz,
        sweeps_per_frame=1,
        start_point=0,
        num_points=1,
        step_length=1,
        double_buffering=True,
    )
    _stress_session(client, config)


def short_pauses(client: a121.Client) -> None:
    _pauses(client, pause_time=0.25)


def long_pauses(client: a121.Client) -> None:
    _pauses(client, pause_time=1.5)


def _pauses(client: a121.Client, *, pause_time: float) -> None:
    config = a121.SensorConfig(
        hwaas=1,
        profile=a121.Profile.PROFILE_5,
        prf=a121.PRF.PRF_13_0_MHz,
        sweeps_per_frame=1,
        start_point=0,
        num_points=500,
        step_length=1,
        frame_rate=100.0,
    )
    _stress_session(client, config, pause_time=pause_time)


def _stress_session(
    client: a121.Client,
    config: a121.SensorConfig,
    *,
    pause_time: t.Optional[float] = None,
) -> None:
    if pause_time is None:
        pause_interval = None
    else:
        pause_interval = pause_time * 2

    client.setup_session(config)
    client.start_session()

    n = 0
    last_pause = time.monotonic()

    while True:
        client.get_next()

        n += 1

        now = time.monotonic()
        if pause_interval is not None and (now - last_pause) > pause_interval:
            last_pause = now
            assert pause_time is not None
            time.sleep(pause_time)

        stats = client._rate_stats

        bits_per_point = 32
        points_per_frame = config.num_points * config.sweeps_per_frame
        effective_bitrate = stats.rate * points_per_frame * bits_per_point

        print_status(
            " | ".join(
                [
                    f"{n:8}",
                    f"{stats.rate:7.1f} Hz",
                    f"{stats.jitter * 1e6:7.1f} us jitter",
                    f"{effective_bitrate * 1e-6:7.1f} Mbit/s",
                ]
            )
        )


def print_status(s: str) -> None:
    now = time.monotonic()
    last_time = getattr(print_status, "last_time", -1)
    dt = now - last_time

    if dt < 0.25:
        return

    setattr(print_status, "last_time", now)
    print(s, end="\r", flush=True)


if __name__ == "__main__":
    main()
