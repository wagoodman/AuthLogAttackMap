""" Acts as a client to the AuthLogWatcher and a webserver to display the
latest event data (over SSE).
"""

# GEvent first...
import gevent
import gevent.monkey
from gevent.pywsgi import WSGIServer
gevent.monkey.patch_all()

# All others...
from flask import Flask, request, Response, render_template, send_from_directory
import sys
import json
import Queue
import string
import random
import logging

# App modules
import rpcClient

app = Flask(__name__)

# Logging...
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s [%(name)s] %(levelname)s : %(message)s'))
handler.setLevel(logging.DEBUG)
rootLogger = logging.getLogger()
rootLogger.addHandler(handler)
rootLogger.setLevel(logging.DEBUG)

clientLogger = logging.getLogger("AuthLogClient")
streamLogger = logging.getLogger("StreamClient")
app.logger.addHandler(handler)

client = None

def generateId(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

def eventStream():
    clientId = generateId()
    streamLogger.info("Streaming to client: %s" % repr(clientId))

    queue = Queue.Queue()

    event = { "eventCount": client.eventCount }
    responseStr = "event: init\ndata: "+json.dumps(event)+"\n\n"
    yield responseStr

    try:
        for event in client.getEvents(queue):
            if event:
                responseStr = "event: auth\ndata: "+json.dumps(event)+"\n\n"
                yield responseStr
    except GeneratorExit:
        raise
    except:
        import traceback
        traceback.print_exc()
    finally:
        streamLogger.info("Removing client stream: %s" % repr(clientId))
        client.removeQueue(queue)

@app.route('/js/<path:path>')
def send_js(path):
    return send_from_directory('js', path)

@app.route('/css/<path:path>')
def send_css(path):
    return send_from_directory('css', path)

@app.route('/svg/<path:path>')
def send_svg(path):
    return send_from_directory('svg', path)

@app.route('/auth')
def sse_request():
    return Response(
            eventStream(),
            mimetype='text/event-stream')

@app.route('/')
def page():
    return render_template('sse.html')


if __name__ == '__main__':
    # subscribe to the auth.log events
    model = rpcClient.AuthLogModel()
    client = rpcClient.AuthLogClient(model)
    client.subscribe()

    # Host a flask server
    host, port = ('0.0.0.0', 80)
    rootLogger.info("Serving HTTP at %s:%d" % (host, port))
    http_server = WSGIServer((host, port), app)

    try:
        http_server.serve_forever()
    except:
        rootLogger.critical("Fatal Error!", exc_info=True)
    finally:
        client.unsubscribe()
    rootLogger.info("Exiting.")
