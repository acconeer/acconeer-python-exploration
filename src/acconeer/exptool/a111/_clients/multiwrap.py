# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from acconeer.exptool.a111._clients.base import BaseClient, ClientError


class MultiClientWrapper(BaseClient):
    def __init__(self, clients, **kwargs):
        kwargs["squeeze"] = False
        super().__init__(**kwargs)
        self.clients = clients

        for client in clients:
            client.squeeze = False

    def _connect(self):
        for client in self.clients:
            info = client.connect()

        return info

    def _setup_session(self, config):
        expected_sensors = [i + 1 for i in range(len(self.clients))]

        if config.sensor != expected_sensors:
            raise ClientError("Invalid sensor selection for multi client wrapper")

        config.sensor = 1

        for client in self.clients:
            info = client.setup_session(config)

        config.sensor = expected_sensors

        return info

    def _start_session(self):
        for client in self.clients:
            client.start_session()

    def _get_next(self):
        all_info = []
        all_data = []
        for client in self.clients:
            info, data = client.get_next()
            all_info.extend(info)
            all_data.append(data)

        return all_info, np.concatenate(all_data)

    def _stop_session(self):
        for client in self.clients:
            client.stop_session()

    def _disconnect(self):
        for client in self.clients:
            client.disconnect()
