from SimpleXMLRPCServer import SimpleXMLRPCServer
from random import randint
import threading
import xmlrpclib
import operator
import argparse
import logging
import Queue
import sys
import os

HISTORY_LENGTH = 500

class AuthLogClient(threading.Thread):
    """ Acts as a client to the AuthLogWatcher. This client class is responsible
    for starting subscriptions over the XMLRPC connection hosted by the server
    and providing another XMLRPC connection for the server to respond with (served
    on a random port in another thread). As events are received external callers
    can get the latest events from the getEvents() generator. Each external
    caller uses an independent queue for storing events before they are read.
    """

    def __init__(self, model):
        super(AuthLogClient, self).__init__()
        self.daemon = True
        self.model = model
        self.eventHistory = list()
        self.eventCount = 0
        self.logger = logging.getLogger("AuthLogClient")

        # Provide a channel of communication to receive events
        self.host, self.port = 'localhost', randint(5000,20000)
        self.queues = list()
        self.server = SimpleXMLRPCServer((self.host, self.port), logRequests=False, allow_none=True)

    def subscribe(self):
        """ Start serving the thread to receive events, the thread will subscribe
        to the server.
        """
        self.start()

    def unsubscribe(self):
        """ Stop serving the thread to receive events, the thread will unsubscribe
        from the server.
        """
        self.model.unsubscribe(self.host, self.port)
        self.server.server_close()

    def getEvents(self, queue):
        """ A generator function which returns a single auth.log event at a time
        from the server. The given queue is used for the caller only, in this way
        multiple callers can be serviced without having to share the same queue
        (otherwise the callers would round-robin the queue when pulling events).
        """

        # Each new caller gets a queue
        self.queues.append(queue)

        # Add known history to the queue for the caller to fetch
        for eventData in self.eventHistory:
            queue.put(eventData)

        # Allow the reader to keep getting events as they arrive.
        try:
            while True:
                try:
                    yield queue.get(block=True, timeout=1)
                except Queue.Empty:
                    pass
                except GeneratorExit:
                    raise
                except:
                    self.logger.critical( "Error generating events!", exc_info=True)
                    raise
        finally:
            # always remove this caller's queue from the list of active queues
            # upon exiting this method.
            self.removeQueue(queue)

    def removeQueue(self, queue):
        """ Remove the queue from the set of active queues.
        """
        if queue in self.queues:
            self.queues.remove(queue)

    def event(self, data):
        """ And event from the server over RPC has arrived!
        """
        self.eventCount += 1
        for queue in self.queues:
            queue.put(data)

    def run(self):
        """ Subscription management thread run method.
        """

        # Subscribe to events
        self.model.subscribe(self.host, self.port)

        # Expose a function
        self.server.register_function(self.event)

        try:
            self.logger.info( "Subscribed to auth.log events! (%s:%d)" % (self.host, self.port))

            # Load history
            self.eventHistory = self.model.getEventHistory(HISTORY_LENGTH)
            self.eventCount += self.model.getEventCount() - len(self.eventHistory)
            self.logger.info( "Fetched History: %d" % len(self.eventHistory))
            self.logger.info( "Total Events: %d" % self.eventCount)

            # Listen for RPC events
            self.server.serve_forever()
        except KeyboardInterrupt:
            print 'Exiting'
        except:
            self.logger.critical( "Error while listening for events from server!", exc_info=True)
        finally:
            self.unsubscribe()



class AuthLogModel(object):
    """ Represents data fetched from the server (AuthLogWatcher).
    """
    def __init__(self):
        self.server = xmlrpclib.Server('http://localhost:7080/')

        # play a game for fun!
        if self.server.ping() != "pong":
            raise RuntimeError("Faulty Server!")

        # add the methods available from the server RPC connection
        self.getHostMessages = self.server.getHostMessages
        self.getHostInfo = self.server.getHostInfo
        self.subscribe = self.server.subscribe
        self.unsubscribe = self.server.unsubscribe
        self.getEventHistory = self.server.getEventHistory
        self.getEventCount = self.server.getEventCount

class AuthLogView(object):
    """ Takes data from the model and massages a presentable string to display.
    """
    def showSummary(self, hostMessages, hostInfo):

        for host in sorted(hostMessages.keys()):

            hostInfoStr = ": "
            try:
                hostObj = hostInfo[host]
                locTemplate = "%s, %s (%s)"
                location = locTemplate % (hostObj["city"],
                                          hostObj["region"],
                                          hostObj["country"])
                hostInfoStr += location + ": " + hostObj["org"]
            except KeyError:
                hostInfoStr += "No info."

            print host + hostInfoStr
            messageCounts = hostMessages[host]
            sortedmessageCounts = sorted(hostMessages[host].items(),
                                        key=operator.itemgetter(1), reverse=True)

            print "    %-5s %s" % ("Count", "Message")
            print "    %-5s %s" % ("-----", "-"*50)
            for message, count in sortedmessageCounts:
                print "    %5s: %s" % (str(count), repr(message))
            print

        print
        print len(hostMessages.keys()),"Hosts"

    def showByCountry(self, hostMessages, hostInfo):
        hostDetails = {}
        for host in sorted(hostMessages.keys()):
            hostItems = []
            for item in ("country", "region", "city", "org"):
                hostValue = "??"
                hostObj = hostInfo[host]
                if item in hostObj and len(hostObj[item].strip()) > 0:
                    hostValue = hostObj[item]
                hostItems.append(hostValue)

            hostItems = tuple(hostItems)
            if hostItems not in hostDetails:
                hostDetails[hostItems] = set()

            hostDetails[hostItems].add(host)

        for key in sorted(hostDetails.keys(), key=operator.itemgetter(0,1,2)):
            (country, region, city, org) = key
            hosts = hostDetails[key]
            hostInfoStr = "%-2s: %15s, %-20s %-50s %-30s" % (country, city,
                                region, org, "%s"%", ".join(sorted(hosts)))

            print hostInfoStr




class AuthLogClientController(object):
    """ CLI access for the client.
    """
    def __init__(self):
        parser = argparse.ArgumentParser(
            description='Query /var/log/auth.log listener.',
            usage='''app [<command>] [<args>]

Valid commands:
   summary    Show a summary of hosts in the auth log (Default)
   country    Show the breakdown of entries by country
   subscribe  Show json events as they occur in realtime
''')
        parser.add_argument('command', nargs='?', default="summary", help='Subcommand to run')

        # parse_args defaults to [1:] for args, but you need to
        # exclude the rest of the args too, or validation will fail
        args = parser.parse_args(sys.argv[1:2])

        if not hasattr(self, args.command):
            print 'Unrecognized command'
            parser.print_help()
            exit(1)

        # Setup the RPC connection
        self.presenter = AuthLogView()
        self.model = AuthLogModel()

        # Dispatch the command to a method
        getattr(self, args.command)()

    def summary(self):
        hostMessages = self.model.getHostMessages()
        hostInfo = self.model.getHostInfo()
        self.presenter.showSummary(hostMessages,
                                   hostInfo)

    def country(self):
        hostMessages = self.model.getHostMessages()
        hostInfo = self.model.getHostInfo()
        self.presenter.showByCountry(hostMessages,
                                     hostInfo)

    def subscribe(self):
        subscriber = AuthLogClient(self.model)
        subscriber.subscribe()
        try:
            for event in subscriber.getEvents():
                print event
        except KeyboardInterrupt:
            pass
        finally:
            print "Unsubscribing..."
            subscriber.unsubscribe()
            print "Done!"
        print "Exiting."

    """
    def commit(self):
        parser = argparse.ArgumentParser(
            description='Record changes to the repository')
        # prefixing the argument with -- means it's optional
        parser.add_argument('--amend', action='store_true')
        # now that we're inside a subcommand, ignore the first
        # TWO argvs, ie the command (git) and the subcommand (commit)
        args = parser.parse_args(sys.argv[2:])
        print 'Running git commit, amend=%s' % args.amend

    def fetch(self):
        parser = argparse.ArgumentParser(
            description='Download objects and refs from another repository')
        # NOT prefixing the argument with -- means it's not optional
        parser.add_argument('repository')
        args = parser.parse_args(sys.argv[2:])
        print 'Running git fetch, repository=%s' % args.repository
    """

if __name__ == "__main__":
    AuthLogClientController()
