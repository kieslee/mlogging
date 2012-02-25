from logging import Handler, StreamHandler, FileHandler
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import fcntl, time, os, codecs, string, re, types, cPickle, struct, shutil
from stat import ST_DEV, ST_INO, ST_MTIME


class StreamHandler_MP(StreamHandler):
    """
    A handler class which writes logging records, appropriately formatted,
    to a stream. Use for multiprocess.
    """
    
    def emit(self, record):
        """
        Emit a record.
            First seek the end of file for multiprocess to log to the same file
        """
        try:
            if hasattr(self.stream, "seek"):
                self.stream.seek(0, os.SEEK_END)
        except IOError, e:
            pass
        
        StreamHandler.emit(self, record)


class FileHandler_MP(FileHandler, StreamHandler_MP):
    """
    A handler class which writes formatted logging records to disk files 
        for multiprocess
    """
    def emit(self, record):
        """
        Emit a record.

        If the stream was not opened because 'delay' was specified in the
        constructor, open it before calling the superclass's emit.
        """
        if self.stream is None:
            self.stream = self._open()
        StreamHandler_MP.emit(self, record)


class RotatingFileHandler_MP(RotatingFileHandler, FileHandler_MP):
    """
    Handler for logging to a set of files, which switches from one file
    to the next when the current file reaches a certain size.
    """
    _lock_dir = '.lock'
    if os.path.exists(_lock_dir):
        pass
    else:
        os.mkdir(_lock_dir)

    def doRollover(self):
        """
        Do a rollover, as described in __init__().
        For multiprocess, we use shutil.copy instead of rename.
        """

        self.stream.close()
        if self.backupCount > 0:
            for i in range(self.backupCount - 1, 0, -1):
                sfn = "%s.%d" % (self.baseFilename, i)
                dfn = "%s.%d" % (self.baseFilename, i + 1)
                if os.path.exists(sfn):
                    if os.path.exists(dfn):
                        os.remove(dfn)
                    shutil.copy(sfn, dfn)
            dfn = self.baseFilename + ".1"
            if os.path.exists(dfn):
                os.remove(dfn)
            if os.path.exists(self.baseFilename):
                shutil.copy(self.baseFilename, dfn)
        self.mode = 'w'
        self.stream = self._open()
        
    
    def emit(self, record):
        """
        Emit a record.

        Output the record to the file, catering for rollover as described
        in doRollover().
        
        For multiprocess, we use file lock.
        """
        try:
            if self.shouldRollover(record):
                self.doRollover()
            FileLock = self._lock_dir + '/' + os.path.basename(self.baseFilename) + '.' + record.levelname
            f = open(FileLock, "w+")
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            FileHandler_MP.emit(self, record)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            f.close()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)
    
        
class TimedRotatingFileHandler_MP(FileHandler_MP):
    """
    Handler for logging to a file, rotating the log file at certain timed
    intervals.

    If backupCount is > 0, when rollover is done, no more than backupCount
    files are kept - the oldest ones are deleted.
    """
    _lock_dir = '.lock'
    if os.path.exists(_lock_dir):
        pass
    else:
        os.mkdir(_lock_dir)
    
    def __init__(self, filename, when='h', interval=1, backupCount=0, encoding=None, delay=0, utc=0):
        FileHandler_MP.__init__(self, filename, 'a', encoding, delay)
        self.mode = mode
        self.encoding = encoding
        self.when = string.upper(when)
        self.backupCount = backupCount
        self.utc = utc
        # Calculate the real rollover interval, which is just the number of
        # seconds between rollovers.  Also set the filename suffix used when
        # a rollover occurs.  Current 'when' events supported:
        # S - Seconds
        # M - Minutes
        # H - Hours
        # D - Days
        # midnight - roll over at midnight
        # W{0-6} - roll over on a certain day; 0 - Monday
        #
        # Case of the 'when' specifier is not important; lower or upper case
        # will work.
        currentTime = int(time.time())
        if self.when == 'S':
            self.interval = 1 # one second
            self.suffix = "%Y-%m-%d_%H-%M-%S"
            self.extMatch = r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$"
        elif self.when == 'M':
            self.interval = 60 # one minute
            self.suffix = "%Y-%m-%d_%H-%M"
            self.extMatch = r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}$"
        elif self.when == 'H':
            self.interval = 60 * 60 # one hour
            self.suffix = "%Y-%m-%d_%H"
            self.extMatch = r"^\d{4}-\d{2}-\d{2}_\d{2}$"
        elif self.when == 'D' or self.when == 'MIDNIGHT':
            self.interval = 60 * 60 * 24 # one day
            self.suffix = "%Y-%m-%d"
            self.extMatch = r"^\d{4}-\d{2}-\d{2}$"
        elif self.when.startswith('W'):
            self.interval = 60 * 60 * 24 * 7 # one week
            if len(self.when) != 2:
                raise ValueError("You must specify a day for weekly rollover from 0 to 6 (0 is Monday): %s" % self.when)
            if self.when[1] < '0' or self.when[1] > '6':
                raise ValueError("Invalid day specified for weekly rollover: %s" % self.when)
            self.dayOfWeek = int(self.when[1])
            self.suffix = "%Y-%m-%d"
            self.extMatch = r"^\d{4}-\d{2}-\d{2}$"
        else:
            raise ValueError("Invalid rollover interval specified: %s" % self.when)

        self.extMatch = re.compile(self.extMatch)
        self.interval = self.interval * interval # multiply by units requested
        self.rolloverAt = self.computeRollover(int(time.time()))

        #print "Will rollover at %d, %d seconds from now" % (self.rolloverAt, self.rolloverAt - currentTime)

    def computeRollover(self, currentTime):
        """
        Work out the rollover time based on the specified time.
        """
        result = currentTime + self.interval
        # If we are rolling over at midnight or weekly, then the interval is already known.
        # What we need to figure out is WHEN the next interval is.  In other words,
        # if you are rolling over at midnight, then your base interval is 1 day,
        # but you want to start that one day clock at midnight, not now.  So, we
        # have to fudge the rolloverAt value in order to trigger the first rollover
        # at the right time.  After that, the regular interval will take care of
        # the rest.  Note that this code doesn't care about leap seconds. :)
        if self.when == 'MIDNIGHT' or self.when.startswith('W'):
            # This could be done with less code, but I wanted it to be clear
            if self.utc:
                t = time.gmtime(currentTime)
            else:
                t = time.localtime(currentTime)
            currentHour = t[3]
            currentMinute = t[4]
            currentSecond = t[5]
            # r is the number of seconds left between now and midnight
            r = _MIDNIGHT - ((currentHour * 60 + currentMinute) * 60 +
                    currentSecond)
            result = currentTime + r
            # If we are rolling over on a certain day, add in the number of days until
            # the next rollover, but offset by 1 since we just calculated the time
            # until the next day starts.  There are three cases:
            # Case 1) The day to rollover is today; in this case, do nothing
            # Case 2) The day to rollover is further in the interval (i.e., today is
            #         day 2 (Wednesday) and rollover is on day 6 (Sunday).  Days to
            #         next rollover is simply 6 - 2 - 1, or 3.
            # Case 3) The day to rollover is behind us in the interval (i.e., today
            #         is day 5 (Saturday) and rollover is on day 3 (Thursday).
            #         Days to rollover is 6 - 5 + 3, or 4.  In this case, it's the
            #         number of days left in the current week (1) plus the number
            #         of days in the next week until the rollover day (3).
            # The calculations described in 2) and 3) above need to have a day added.
            # This is because the above time calculation takes us to midnight on this
            # day, i.e. the start of the next day.
            if self.when.startswith('W'):
                day = t[6] # 0 is Monday
                if day != self.dayOfWeek:
                    if day < self.dayOfWeek:
                        daysToWait = self.dayOfWeek - day
                    else:
                        daysToWait = 6 - day + self.dayOfWeek + 1
                    newRolloverAt = result + (daysToWait * (60 * 60 * 24))
                    if not self.utc:
                        dstNow = t[-1]
                        dstAtRollover = time.localtime(newRolloverAt)[-1]
                        if dstNow != dstAtRollover:
                            if not dstNow:  # DST kicks in before next rollover, so we need to deduct an hour
                                newRolloverAt = newRolloverAt - 3600
                            else:           # DST bows out before next rollover, so we need to add an hour
                                newRolloverAt = newRolloverAt + 3600
                    result = newRolloverAt
        return result

    def shouldRollover(self, record):
        """
        Determine if rollover should occur.

        record is not used, as we are just comparing times, but it is needed so
        the method signatures are the same
        """
        if not os.path.exists(self.baseFilename):
            #print "file don't exist"  
            return 0 
        
        cTime = time.localtime(time.time()) 
        mTime = time.localtime(os.stat(self.baseFilename)[ST_MTIME])
        if self.when == 'M' and cTime[4] != mTime[4]:  
            #print "cTime:", cTime[4], "mTime:", mTime[4]   
            return 1  
        elif self.when == 'H' and cTime[3] != mTime[3]: 
            #print "cTime:", cTime[3], "mTime:", mTime[3]   
            return 1    
        elif self.when == 'MIDNIGHT' and cTime[2] != mTime[2]:
            #print "cTime:", cTime[2], "mTime:", mTime[2]   
            return 1 
        else:  
            return 0 

        t = int(time.time())
        if t >= self.rolloverAt:
            return 1
        #print "No need to rollover: %d, %d" % (t, self.rolloverAt)
        return 0
    
    def getFilesToDelete(self):
        """
        Determine the files to delete when rolling over.

        More specific than the earlier method, which just used glob.glob().
        """
        dirName, baseName = os.path.split(self.baseFilename)
        fileNames = os.listdir(dirName)
        result = []
        prefix = baseName + "."
        plen = len(prefix)
        for fileName in fileNames:
            if fileName[:plen] == prefix:
                suffix = fileName[plen:]
                if self.extMatch.match(suffix):
                    result.append(os.path.join(dirName, fileName))
        result.sort()
        if len(result) < self.backupCount:
            result = []
        else:
            result = result[:len(result) - self.backupCount]
        return result

    def doRollover(self):
        """
        do a rollover; in this case, a date/time stamp is appended to the filename
        when the rollover happens.  However, you want the file to be named for the
        start of the interval, not the current time.  If there is a backup count,
        then we have to get a list of matching filenames, sort them and remove
        the one with the oldest suffix.
        """
        if self.stream:
            self.stream.close()
        # get the time that this sequence started at and make it a TimeTuple
        #t = self.rolloverAt - self.interval
        t = int(time.time())
        if self.utc:
            timeTuple = time.gmtime(t)
        else:
            timeTuple = time.localtime(t)
        dfn = self.baseFilename + "." + time.strftime(self.suffix, timeTuple)
        if os.path.exists(dfn):
            os.remove(dfn)
        if os.path.exists(self.baseFilename):
            shutil.copy(self.baseFilename, dfn)
            #print "%s -> %s" % (self.baseFilename, dfn)
            #os.rename(self.baseFilename, dfn)
        if self.backupCount > 0:
            # find the oldest log file and delete it
            #s = glob.glob(self.baseFilename + ".20*")
            #if len(s) > self.backupCount:
            #    s.sort()
            #    os.remove(s[0])
            for s in self.getFilesToDelete():
                os.remove(s)
        self.mode = 'w'
        self.stream = self._open()
        #self.stream.truncate(0)
        currentTime = int(time.time())
        newRolloverAt = self.computeRollover(currentTime)
        while newRolloverAt <= currentTime:
            newRolloverAt = newRolloverAt + self.interval
        #If DST changes and midnight or weekly rollover, adjust for this.
        if (self.when == 'MIDNIGHT' or self.when.startswith('W')) and not self.utc:
            dstNow = time.localtime(currentTime)[-1]
            dstAtRollover = time.localtime(newRolloverAt)[-1]
            if dstNow != dstAtRollover:
                if not dstNow:  # DST kicks in before next rollover, so we need to deduct an hour
                    newRolloverAt = newRolloverAt - 3600
                else:           # DST bows out before next rollover, so we need to add an hour
                    newRolloverAt = newRolloverAt + 3600
        self.rolloverAt = newRolloverAt
    
    def emit(self, record):
        """
        Emit a record.

        Output the record to the file, catering for rollover as described
        in doRollover().
        """
        try:
            if self.shouldRollover(record):
                self.doRollover()
            FileLock = self._lock_dir + '/' + os.path.basename(self.baseFilename) + '.' + record.levelname
            f = open(FileLock, "w+")
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            FileHandler_MP.emit(self, record)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            f.close()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)
        