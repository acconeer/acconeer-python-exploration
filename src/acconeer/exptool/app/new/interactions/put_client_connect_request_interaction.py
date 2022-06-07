from acconeer.exptool import a121
from acconeer.exptool.app.new.app_model import AppModel

from .response import Success


def put_client_connect_request(app_model: AppModel, client_info: a121.ClientInfo) -> Success[None]:
    app_model.connect_client(client_info)
    return Success(None, None, None)
