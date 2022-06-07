from acconeer.exptool.app.new.app_model import AppModel

from .response import Success


def put_client_disconnect_request(app_model: AppModel) -> Success[None]:
    app_model.disconnect_client()
    return Success(None, None, None)
