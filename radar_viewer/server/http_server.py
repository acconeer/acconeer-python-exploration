from functools import wraps, update_wrapper
from datetime import datetime
from server.demo_control import DemoControl
from server.detector_wrappers import EnvelopeHandler, IQHandler, PowerBinHandler

from threading import Thread
from threading import Timer

import flask
from flask import request
import os
import signal

# TODO: The Flask framework does not support a global shared state like the demo_ctrl object
#       below. It seems to work anyway when using the build in development server. For better
#       reliability and scaling this file should be rewritten for another framework, e.g.
#       Twisted, that is better suited for handling a common state that is shared between
#       different http sessions.
demo_ctrl = DemoControl()

app = flask.Flask(__name__, static_url_path="/static")


def nocache(view):
    @wraps(view)
    def no_cache(*args, **kwargs):
        response = flask.make_response(view(*args, **kwargs))
        response.headers["Last-Modified"] = datetime.now()
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0,"\
                                            " pre-check=0, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "-1"
        return response
    return update_wrapper(no_cache, view)


@app.route("/")
@nocache
def root():
    return app.send_static_file("index.html")


def shutdown_server():
    print("Shutting down")
    os.kill(os.getpid(), signal.SIGINT)


@app.route("/exit", methods=["GET"])
def shutdown():
    t = Timer(1.0, shutdown_server)
    t.start()
    return '{"ok": null}'


@app.route("/<path:path>")
@nocache
def static_file(path):
    return app.send_static_file(path)


def event_stream():
    mess_queue = demo_ctrl.subscribe()
    while True:
        mess = mess_queue.get()
        yield "data:" + mess + "\n\n"


@app.route("/stream")
def stream():
    return flask.Response(event_stream(), mimetype="text/event-stream",
                          headers={"Access-Control-Allow-Origin": "*"})


@app.route("/start/<detector_name>")
def detector_start(detector_name):
    print("got start %s" % detector_name)
    print("params %s" % request.args)
    res = demo_ctrl.start_detector(detector_name, request.args)
    print(request.args)
    return flask.jsonify(res)


@app.route("/stop")
def button_stop():
    res = demo_ctrl.stop_detector()
    return flask.jsonify(res)


@app.route("/rvc/<command>/<value>")
def rvc2(command, value):
    if command in ["start", "stop", "turn"]:
        print("Got command: %s" % command)
        demo_ctrl.put_cmd(["rvc_command", command, value])
        res = {"ok": None}
    else:
        print("Got unknown command: %s" % command)
        res = {"error": "Unknown RVC command: %s" % command}
    return flask.jsonify(res)


def worker_thread_main_loop():
    while demo_ctrl.process_next():
        pass
    print("Worker thread stopped")


def stop_server():
    demo_ctrl.put_cmd(["exit"])


def start_server(args):
    old_handler = signal.getsignal(signal.SIGINT)

    def signal_handler(sig, frame):
        print("CTRL-C pressed!")
        stop_server()
        old_handler(sig, frame)

    signal.signal(signal.SIGINT, signal_handler)

    demo_ctrl.set_streaming_client_args(args)

    demo_ctrl.add_detector(PowerBinHandler)
    demo_ctrl.add_detector(EnvelopeHandler)
    demo_ctrl.add_detector(IQHandler)

    main_loop_worker = Thread(target=worker_thread_main_loop)
    main_loop_worker.start()

    app.run(host="localhost", threaded=True)
    print("http server stopped")
