from twisted.web import xmlrpc
import xmlrpclib
import operator

class XMLRPCSubscriber(object):
    """ Represents a client which is subscribing to content over XMLRPC. The
    client serves a XMLRPC port which the auth.log watcher uses to send
    new auth events.
    """

    def __init__(self, host, port):
        self.server = xmlrpclib.Server('http://%s:%s/'%(str(host), str(port)))

    def sendEvent(self, data):
        self.server.event(data)

class AuthXMLRPCResponder(xmlrpc.XMLRPC, object):
    """ The published API over RPC to facilitate auth log subscriptions.
    """

    def __init__(self, watcher):
        super(AuthXMLRPCResponder, self).__init__(allowNone=True)
        self.watcher = watcher

    def xmlrpc_ping(self):
        return "pong"

    # Fetching data stores

    def xmlrpc_getEventCount(self):
        return self.watcher.eventCount

    def xmlrpc_getHostMessages(self):
        return self.watcher.hostMessages

    def xmlrpc_getHostInfo(self):
        return self.watcher.hostInfo

    def xmlrpc_getEventHistory(self, length):
        if len(self.watcher.eventHistory) > length:
            return self.watcher.eventHistory[-length:]
        return self.watcher.eventHistory

    # Facilitating subscriptions to clients

    def xmlrpc_subscribe(self, url, port):
        self.watcher.subscribe( (url, port), XMLRPCSubscriber(url, port) )

    def xmlrpc_unsubscribe(self, url, port):
        self.watcher.unsubscribe( (url, port) )
