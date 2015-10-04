from twisted.internet import reactor
import cPickle as pickle
import requests
import logging
import time
import json
import re

import fileWatcher
import publisher

# Patterns to search for in line events (from the auth.log)
sshPattern = re.compile(r'.*sshd\[\d+\]: (?P<message>.*)')
ipPattern = re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
portPattern = re.compile(r'.* port (?P<port>\d+).*')
quotedPattern = re.compile(r"['\"].+['\"]")

# Misc.
cacheFile = "hostInfo.cache"
HISTORY_LENGTH = 4000

class AuthLogWatcher(fileWatcher.FileWatcher, publisher.Publisher):
    """
    Watches events written to the auth.log, parses each event, and adds the
    event/host info to internal stores. Note: 192.168.* addresse are ignored!

    The AuthLogWatcher (this class) accepts subscriptions from clients wishing
    to get auth.log event updates (AuthLogClients). The clients setup an RPC
    connection for the watcher to respond on.

    AuthLogWatcher                AuthLogClient
         |                               |
         x (start server)                |
         | <---- connect & subscribe --- |
    ---> x (auth.log event)              |
         | ---- sendEvent() -----------> |
         |                               | ---> (display)
         ...                             ...

    """

    watchPath = "/var/log/auth.log"

    # set of IP addresses
    observedHosts = None

    # set of "accepted" addresses
    acceptedHosts = None

    # { host : { message : count }}
    hostMessages = None

    # { host : {response} }
    hostInfo = None

    # [ Subscriber objects ]
    subscribers = None

    # Event count
    eventCount = 0

    def __init__(self):
        self.hostMessages = {}
        self.eventHistory = []

        self.logger = logging.getLogger("AuthLogWatcher")
        self.hostInfo = self.getCache()

        fileWatcher.FileWatcher.__init__(self, self.watchPath)
        publisher.Publisher.__init__(self)

    def getCache(self):
        """ Fetches hostInfo cache from disk.
        """
        hostInfo = {}
        try:
            with open(cacheFile, 'rb') as handle:
                hostInfo = pickle.load(handle)
        except:
            self.logger.warning("Unable to load cache.")
        return hostInfo

    def saveCache(self):
        """ Writes hostInfo cache to disk.
        """
        try:
            with open(cacheFile, 'wb') as handle:
                pickle.dump(self.hostInfo, handle)
        except:
            self.logger.warning("Unable to save cache.")

    def addEvent(self, host, message):
        """ Record the event to data store, specifically taking note of the
        number of times the message has been observed.
        """
        # add host
        if host not in self.hostMessages:
            self.hostMessages[host] = {}

        # add message
        if message not in self.hostMessages[host]:
            self.hostMessages[host][message] = 0

        # count!
        self.hostMessages[host][message] += 1

    def addHostInfo(self, ipAddress):
        """ Record the host info to data store. If this is a novel host, then
        the IP info is fetched from ipinfo.io.
        """
        try:
            if ipAddress not in self.hostInfo:
                retObj = requests.get("http://ipinfo.io/"+ipAddress+"/json")
                if retObj.status_code == 200:
                    self.hostInfo[ipAddress] = retObj.json()
                    print self.displayHostInfo(ipAddress)
                else:
                    self.logger.warning("Non-200 HTTP response while fetching IP Info!")
        except:
            self.logger.warning("Error while fetching IP Info!", exc_info=True)
            raise

    def displayHostInfo(self, ipAddress):
        """ Return a string representing the host information for the given address.
        """
        hostInfoStr = "   "+ipAddress+" : "
        try:
            hostObj = self.hostInfo[ipAddress]
            locTemplate = "%s, %s (%s)"
            location = locTemplate % (hostObj["city"],
                                      hostObj["region"],
                                      hostObj["country"])
            hostInfoStr += location + ": " + hostObj["org"]
        except KeyError:
            hostInfoStr += "No info."

        return hostInfoStr

    def handleLine(self, line):
        """ Parse the given auth.log line and return an event object to be published.
        """
        sshMatch = sshPattern.search(line)

        # Only match on sshd events
        if sshMatch:
            message = sshMatch.group('message')
            sanitizedMessage = quotedPattern.sub('', message)

            ipAddress = None
            ipPort = None

            # Determine if there is an IP address in the line
            ipMatch = ipPattern.search(message)
            if ipMatch:
                ipAddress = ipMatch.group(0)
                sanitizedMessage = sanitizedMessage.replace(ipAddress, "")

                # Not interested in local boxes access
                if "192.168." in ipAddress:
                    return

            # Determine if there is an IP port in the line
            portMatch = portPattern.search(message)
            if portMatch:
                ipPort = portMatch.group('port')
                sanitizedMessage = sanitizedMessage.replace(ipPort, "")

            # Take action if there was a remote auth.log event
            if ipAddress:
                # Add host & host info to the store
                self.addEvent(ipAddress, sanitizedMessage)
                self.addHostInfo(ipAddress)

                # Log the action
                hostStr = self.displayHostInfo(ipAddress)
                self.logger.info("Processed Line: %s\n%s" % (str(line),
                                                             str(hostStr)))

                # Make event data for publishing
                eventData = { "time": time.time(),
                              "hostinfo": self.hostInfo[ipAddress],
                              "message": message
                }

                self.eventCount += 1

                return eventData


    def lineReceived(self, line):
        """ Respond to the inotify event by passing any newly observed
        lines to the handler thread.
        """
        try:
            eventData = self.handleLine(line)

            if eventData:
                # Store history
                self.eventHistory.append(eventData)
                while len(self.eventHistory) > HISTORY_LENGTH:
                    self.eventHistory.pop(0)

                # Notify subscribers
                for key, subscriber in self.subscribers.items():
                    try:
                        subscriber.sendEvent(eventData)
                    except:
                        # unsubscrive dead clients
                        self.logger.warning("Dead client: %s" % repr(key))
                        self.unsubscribe(key)
        except:
            self.logger.critical("Error receiving line!", exc_info=True)
            raise
