from twisted.internet import reactor
from twisted.web import server
import logging
import sys
reload(sys)
sys.setdefaultencoding("utf-8")

# App modules
import authLogWatcher
import rpcServe

# Logging...
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s [%(name)s] %(levelname)s : %(message)s'))
handler.setLevel(logging.DEBUG)
rootLogger = logging.getLogger()
rootLogger.addHandler(handler)
rootLogger.setLevel(logging.DEBUG)

appLogger = logging.getLogger("AuthLogWatcher")


# Get ready...
watcher = authLogWatcher.AuthLogWatcher() # setup the auth.log watcher
watcher.start() # start watching the auth.log
clientResponder = rpcServe.AuthXMLRPCResponder(watcher) # setup the client protocol
reactor.listenTCP(7080, server.Site(clientResponder) ) # accept clients

# Go!...
try:
    reactor.run()
except KeyboardInterrupt:
    print "KeyboardInterrupt"
except:
    appLogger.critical("Fatal", exc_info=True)
finally:
    watcher.saveCache()
print "Bye!"
