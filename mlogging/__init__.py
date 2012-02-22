import logging, inspect, socket, os
import handlers
from handlers import getRotatingHandler, MailHandler
from singleton import Singleton
from threading import Lock
import sys, cStringIO, traceback

lock_config = Lock()

import fcntl
LOCKFILE_DEBUG = ".lock/lock_file.debug"
LOCKFILE_INFO = ".lock/lock_file.info"
LOCKFILE_WARNING = ".lock/lock_file.warning"
LOCKFILE_ERROR = ".lock/lock_file.error"
LOCKFILE_CRITICAL = ".lock/lock_file.critical"

############### ucmlogging module ###############
class ucmlogging(Singleton):
    # some global variables
    level_list = ('debug', 'info', 'warning', 'error', 'critical')
    logger_list = {'debug': logging.getLogger('ucmlogging.debug'),
                    'info': logging.getLogger('ucmlogging.info'),
                    'warning': logging.getLogger('ucmlogging.warning'),
                    'error': logging.getLogger('ucmlogging.error'),
                    'critical': logging.getLogger('ucmlogging.critical')
    }
    handler_list = {}
    mail_handler = None
    lock = Lock()

    # extra data to be stored in ucmlogging, defined in dic{}
    dic = {'clientip' : socket.gethostname()}
    try:
        f = open('/proc/' + str(os.getpid()) + '/cmdline', 'r')
        pn = f.readline()
        f.close()
    except:
        pn = None
        f.close()
    dic['psname'] = pn.replace('\000','#')[:-1]
    
    # set logfile
    base_config = {
        'logfile' : 'ucm.log',
        'classify' : True,
        'minpriority' : 10,
        'viamail' : 0,
        'mailaddr' : ''
    }
    
    # rotate settings
    rotate_config = {
        'ro_rotateby' : 1,
        'ro_backupcount' : 4,
        'ro_maxsize' : 1024*1024*10,
        'ro_when' : 'midnight',
        'ro_interval' : 1,
        'multiprocess' : 0
    }

    lock_dir = '.lock'
    
    if os.path.exists(lock_dir):
        pass
    else:
        os.mkdir(lock_dir)

    def __init__(self):
        #self.logdir = './' + os.path.dirname(inspect.stack()[2][1]) + '/log'
        self.logdir = os.getcwd() + '/log'

    def validate_base_config(self):
        if not isinstance(self.base_config['logfile'], str):
            raise TypeError('logfile: parameter is not str')
        if not isinstance(self.base_config['classify'], bool):
            raise TypeError('classify: parameter is not bool')
        if self.base_config['minpriority'] not in (10, 20, 30, 40, 50):
            raise ValueError('minpriority: parameter is not valid')
        if not isinstance(self.base_config['viamail'] , int):
            raise ValueError('viamail: parameter is not int')
        if not isinstance(self.base_config['mailaddr'], str):
            raise ValueError('mailaddr: parameter is not str')
        
    def validate_rotate_config(self):
        if self.rotate_config['ro_rotateby'] not in (1, 2):
            raise ValueError('ro_rotateby: value is not valid')

        if not isinstance(self.rotate_config['ro_backupcount'], int):
            raise TypeError('ro_backupcount: parameter is not int')

        if self.rotate_config['ro_backupcount'] <= 0:
            raise ValueError('ro_backupcount: should not lower than or equal to zero')
            
        if not (isinstance(self.rotate_config['ro_maxsize'], int) or isinstance(self.rotate_config['ro_maxsize'], float)):
            raise TypeError('ro_maxsize: parameter is neither int nor float')

        if self.rotate_config['ro_maxsize'] <= 0:
            raise ValueError('ro_maxsize: should not lower than or equal to zero')

        # 'S' Secondes; 'M' Minutes; 'H' Hours; 'D' Days; 'W' Week day(0=Monday); 'midnight' roll over at midnight
        #if self.rotate_config['ro_when'] not in ('S', 'M', 'H', 'D', 'W', 'MIDNIGHT'):
        #    raise ValueError('ro_when: is not in (S, M, H, D, W, midnight)')
        # only support form "M, H, midnight", modified by chenweiguo @20111230 for python 2.6.5 logging module rotate
        if self.rotate_config['ro_when'] not in ('M', 'H', 'MIDNIGHT'):
            raise ValueError('ro_when: is not in (M, H, midnight)')

        if not isinstance(self.rotate_config['ro_interval'], int):
            raise TypeError('ro_interval: parameter is not int')

        if self.rotate_config['ro_interval'] <= 0:
            raise ValueError('ro_interval: should not lower than or equal to zero')
        
        if not isinstance(self.rotate_config['multiprocess'], int):
            raise ValueError('multiprocess: parameter is not int')
        
        if self.rotate_config['multiprocess'] < 0:
            raise ValueError('multiprocess: should not lower than zero')

    def setConfig(self,
                    module_name='',
                    ro_rotateby=1,
                    ro_backupcount=4,
                    ro_maxsize=1024*1024*10,
                    ro_when='midnight',
                    ro_interval=1,
                    logfile='ucm.log',
                    classify=True,
                    minpriority=10,
                    multiprocess=0,
                    viamail=0,
                    mailaddr=''):
                    
        if not isinstance(module_name, str):
            raise TypeError('module_name: parameter is not str')
        self.dic['module_name'] = module_name

        #### set the rotate configuration
        self.rotate_config['ro_rotateby'] = ro_rotateby # 1 by file size; 2 by date
        self.rotate_config['ro_backupcount'] = ro_backupcount
        self.rotate_config['ro_maxsize'] = ro_maxsize
        # You can use the when to specify the type of interval.
        # 'S' Secondes; 'M' Minutes; 'H' Hours; 'D' Days; 'W' Week day(0=Monday); 'midnight' roll over at midnight
        self.rotate_config['ro_when'] = ro_when.upper()
        self.rotate_config['ro_interval'] = ro_interval
        
        self.rotate_config['multiprocess'] = multiprocess
        
        self.validate_rotate_config()
        handlers.setRotate(self.rotate_config)

        self.base_config['logfile'] = logfile
        self.base_config['classify'] = classify
        self.base_config['minpriority'] = minpriority
        self.base_config['viamail'] = viamail
        self.base_config['mailaddr'] = mailaddr
        
        self.validate_base_config()

        self.restart()

    # start configuration
    def start(self):
        if os.path.exists(self.logdir):
            if os.path.isfile(self.logdir): 
                raise Exception('log is a file, not a directory!')
        else:   
            os.mkdir(self.logdir)
        
        try:
            # formating file names
            filename = self.logdir + '/' + self.base_config['logfile']
            dot = filename.find('.log')
            if dot == -1:
                filename = filename + '.log'
                dot = filename.find('.log')
                
            # prepare rotating handlers
            fmt_rf = logging.Formatter(fmt='%(levelname)s: %(asctime)s: %(module_name)s %(psname)s %(process)d [%(clientip)s] [%(fname)s:%(lnumber)dL] %(message)s',datefmt='%m-%d %H:%M:%S')

            if self.base_config['classify']:
                for LEVEL in self.level_list:
                    self.handler_list[LEVEL] = getRotatingHandler('%s_%s%s' % (filename[:dot], LEVEL, filename[dot:]))
                    self.handler_list[LEVEL].setLevel(eval('logging.'+LEVEL.upper()))
                    self.handler_list[LEVEL].setFormatter(fmt_rf)
                    self.logger_list[LEVEL].addHandler(self.handler_list[LEVEL])
            else:
                for LEVEL in self.level_list:
                    level_num = eval('logging.'+LEVEL.upper())
                    if level_num <= 30:
                        self.handler_list[LEVEL] = getRotatingHandler('%s_%s%s' % (filename[:dot], '_warning', filename[dot:]))
                        self.handler_list[LEVEL].setLevel(level_num)
                    else:
                        self.handler_list[LEVEL] = getRotatingHandler('%s_%s%s' % (filename[:dot], '_critical', filename[dot:]))
                        self.handler_list[LEVEL].setLevel(level_num)
                    self.handler_list[LEVEL].setFormatter(fmt_rf)
                    self.logger_list[LEVEL].addHandler(self.handler_list[LEVEL])
                            
            # Mail Handler
            if self.base_config['viamail'] > 0:
                self.mail_handler = MailHandler(self.base_config['mailaddr'])
                self.mail_handler.setFormatter(fmt_rf)
                self.logger_list['critical'].addHandler(self.mail_handler)
            
            # set the log level
            for LEVEL in self.level_list:
                self.logger_list[LEVEL].setLevel(self.base_config['minpriority'])
                
        except Exception, e:
            traceback.print_exc()
            raise e
    
    # stop configuration
    def stop(self):
        for LEVEL in self.level_list:
            tmp_lists = self.logger_list[LEVEL].handlers[:]
            for hdlr in tmp_lists:
                self.logger_list[LEVEL].removeHandler(hdlr)
        
        for key in self.handler_list.keys():
            self.handler_list[key].close()
        self.handler_list = {}


    def restart(self):
        lock_config.acquire()
        self.stop()
        self.start()
        lock_config.release()
    
    def debug(self, msg, *args, **kwargs):
        st = inspect.stack()[1]
        try:                
            dic = self.dic.copy()
            dic['lnumber'] = st[2]
            dic['fname'] = st[1]
            for i in args:
                msg += ' ' + str(i)
            if self.rotate_config['multiprocess'] != 0:
                f = open(LOCKFILE_DEBUG, "w+")
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                
            self.logger_list['debug'].debug(msg , extra=dic)
            
            if self.rotate_config['multiprocess'] != 0:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                f.close()
        except Exception as e:
            raise Exception('error while logging')

    def info(self, msg, *args, **kwargs):
        st = inspect.stack()[1]
        try:                
            dic = self.dic.copy()
            dic['lnumber'] = st[2]
            dic['fname'] = st[1]
            for i in args:
                msg += ' ' + str(i)
            if self.rotate_config['multiprocess'] != 0:
                f = open(LOCKFILE_INFO, "w+")
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                
            self.logger_list['info'].info(msg , extra=dic)
            
            if self.rotate_config['multiprocess'] != 0:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                f.close()
        except Exception as e:
            raise Exception('error while logging')
    
    def warning(self, msg, *args, **kwargs):
        st = inspect.stack()[1]
        try:                
            dic = self.dic.copy()
            dic['lnumber'] = st[2]
            dic['fname'] = st[1]
            for i in args:
                msg += ' ' + str(i)
            if self.rotate_config['multiprocess'] != 0:
                f = open(LOCKFILE_WARNING, "w+")
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                
            self.logger_list['warning'].warning(msg, extra=dic)
            
            if self.rotate_config['multiprocess'] != 0:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                f.close()
        except Exception as e:
            raise Exception('error while logging')

    def error(self, msg, *args, **kwargs):
        st = inspect.stack()[1]
        try:                
            dic = self.dic.copy()
            dic['lnumber'] = st[2]
            dic['fname'] = st[1]
            for i in args:
                msg += ' ' + str(i)
            if self.rotate_config['multiprocess'] != 0:
                f = open(LOCKFILE_ERROR, "w+")
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                
            self.logger_list['error'].error(msg, extra=dic)
            
            if self.rotate_config['multiprocess'] != 0:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                f.close()
        except Exception as e:
            raise Exception('error while logging')

    def exception(self, msg, *args, **kwargs):
        try:    
            ei = sys.exc_info()
            sio = cStringIO.StringIO()
            traceback.print_exception(ei[0], ei[1], ei[2], None, sio)
            s = sio.getvalue()
            sio.close()
            ex = s.replace('\n',' ')
        except Exception, e:
            ex = 'log exception'
        st = inspect.stack()[1]
        try:                
            dic = self.dic.copy()
            dic['lnumber'] = st[2]
            dic['fname'] = st[1]
            for i in args:
                msg += ' ' + str(i)
            self.logger_list['error'].error(ex + " " + msg, extra=dic)
        except Exception as e:
            raise Exception('error while logging')

    def critical(self, msg, *args, **kwargs):
        st = inspect.stack()[1]
        try:                
            dic = self.dic.copy()
            dic['lnumber'] = st[2]
            dic['fname'] = st[1]
            for i in args:
                msg += ' ' + str(i)
            if self.rotate_config['multiprocess'] != 0:
                f = open(LOCKFILE_CRITICAL, "w+") 
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                
            self.logger_list['critical'].critical(msg, extra=dic)
            
            if self.rotate_config['multiprocess'] != 0:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                f.close()
        except Exception as e:
            raise Exception('error while logging')

log = ucmlogging()
#log.setConfig(module_name='module_name')

if __name__ == "__main__":

    debug('hello world')
    warning('hello world')
    info('hello world')
    error('hello world')
    critical('hello world')
