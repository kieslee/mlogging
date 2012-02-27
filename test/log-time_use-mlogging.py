import glob
import logging
import time
from multiprocessing import Process
import signal, os
from mlogging import TimedRotatingFileHandler_MP

LOG_FILENAME = 'log/logging_time.out'

if os.path.exists("log"):
    pass
else:
    os.mkdir("log")

# Set up a specific logger with our desired output level
my_logger = logging.getLogger('MyLogger')
my_logger.setLevel(logging.DEBUG)

# Add the log message handler to the logger
handler = TimedRotatingFileHandler_MP(
              LOG_FILENAME, when='s', interval=1, backupCount=5)

my_logger.addHandler(handler)


def sig_handler(signum,frame):
        print "recv a signal"
        os._exit(0)

def f():
    while True:
        my_logger.debug('f, %s', str(time.time()))
        time.sleep(1)
def g():
    while True:
        my_logger.debug('g, %s', str(time.time()))
        time.sleep(5)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, sig_handler)

    fp = Process(target=f, args=())
    fp.start()

    gp = Process(target=g, args=())
    gp.start()

    fp.join()
    gp.join()
