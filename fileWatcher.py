from twisted.internet import inotify
from twisted.python import filepath
from twisted.protocols.basic import LineReceiver
import logging
import abc
import os

class FileWatcher(LineReceiver, object):
    """
    This class is responsible for tailing a single file by registering the parent
    directory with the iNotify kernel module. This way all file modifications
    and moves regarding this path (e.g. logrotate) are accounted for. This class
    should be inherited by another class which implements the Twisted LineReceiver
    Protocol.

    Note: If you monitor the file of interest directly and the file is swapped
            out for any reason, then any future changes will not be seen since
            the original inode is being used by the inotify module. If the parent
            directory is used, then newly created files which match the path of
            interest will be fully observable.
	"""
    __metaclass__ = abc.ABCMeta

    # This is the filepath which should be monitored
    watchPath = None

    # The file handle to the watch path
    file = None

    # The inotify Object
    notifier = None

    def __init__(self, watchPath):
        self.watchPath = watchPath
        self.logger = logging.getLogger()

    def start(self):
        """ Register the file with iNotify and prep the file handle to the end
        to avoid reading the existing contents.
        """

        # Starting listening
        self.notifier = inotify.INotify()
        self.notifier.startReading()

        # Note: we watch the parent directory for changes to cover log rotate
        # cases. If we only monitor the individual file then there is a chance
        # that we will not see any other changes after the file is moved
        # and recreated (this is a race condition if there is a 'create'
        # clause in the logrotate config and the producing application
        # does not open the file for writing again).

        parentDir = os.path.dirname(self.watchPath)

        # The original watch mask covers the following cases:
        #     IN_MODIFY        File was modified
        #     IN_ATTRIB        Metadata changed
        #     IN_MOVED_FROM  File was moved from X
        #     IN_MOVED_TO     File was moved to Y
        #     IN_CREATE        Subfile was created
        #     IN_DELETE        Subfile was delete
        #     IN_DELETE_SELF Self was deleted
        #     IN_MOVE_SELF    Self was moved
        #     IN_UNMOUNT      Backing fs was unmounted
        self.notifier.watch(filepath.FilePath(str.encode(parentDir)),
                                  callbacks=[self.eventReceived])

        # Seek the the end of the file before processing any new information
        self.openNewFile()


    def openNewFile(self, skipToEnd=False):
        """
        Open a new file handle for the watch path and optionally read to the
        end of the file.
        """
        # Attempt to close the original file gracefully (referenced by inode)
        if self.file:
            try:
                self.file.close()
            except:
                # Catch any errors relating to closing the file as this is a readonly
                # handle
                pass

        try:
            self.logger.debug("Monitoring file for changes (%s)." %
                                    repr(self.watchPath))

            self.file = open(self.watchPath, "r")

            # Ignore previous contents in the file just opened
            if skipToEnd:
                self.file.seek(0,2)

            # Read all existing contents in the file just opened
            else:
                for line in self.file.readlines():
                    self.lineReceived(line.strip())
        except:
            # This should catch any exception regarding file access
            self.logger.warning("Could not open file for monitoring (%s)." % \
                                      repr(self.watchPath),
                                      exc_info=True)


    def eventReceived(self, watch, watchPath, mask):
        """ Callback when iNotify has observed a change in the watch file.
        The remaining file contents are read and passed to the line
        handler (not implemented). Note that the original watch mask
        """
        # Only handle events for the file in question
        if self.watchPath == watchPath.path.decode("utf-8"):
            # Handle logrotate case (the original file is moved and a new file
            # is created with the same path).
            if mask & inotify.IN_CREATE or mask & inotify.IN_MOVED_TO:

                self.logger.info("Monitored file rolled (%s)." %
                                        repr(self.watchPath))

                self.openNewFile(skipToEnd=False)

            # Data has been written to the file.
            elif mask & inotify.IN_MODIFY:

                try:
                    # Continue reading from the current position until the end of the file
                    for line in self.file.readlines():

                        self.lineReceived(line.strip())
                except:
                    # Any error in reading should result in no action taken
                    self.logger.critical("Could not read data from file (%s)." % \
                                                repr(self.watchPath),
                                                exc_info=True)
            else:
                self.logger.debug("Monitored file event (Mask:%s Log:%s)." %
                                      (repr(mask), repr(self.watchPath)))

        else:
            self.logger.debug("General file event (Mask:%s Log:%s)." %
                                      (repr(mask), repr(watchPath.path.decode("utf-8"))))


    @abc.abstractmethod
    def lineReceived(self, line):
        """Take a specific action on a single line observed in the log file.
        """
        pass
