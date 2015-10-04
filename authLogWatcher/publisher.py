import logging

class Publisher(object):
    """
    A simple pub-sub class. The subscriber objects given hold the methods
    necessary for publishing.
    """

    def __init__(self):
        self.logger = logging.getLogger("AuthLogWatcher")
        self.subscribers = {}

    def unsubscribe(self, key):
        if key in self.subscribers:
            self.logger.info( "Lost Subscriber: %s" % repr(key))
            del self.subscribers[key]

    def subscribe(self, key, subscriber):
        self.unsubscribe(key)
        self.logger.info( "New Subscriber: %s" % repr(key))
        self.subscribers[key] = subscriber
