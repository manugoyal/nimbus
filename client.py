import logging
import watchdog
import signal
from util import setup

class Conf:
    FILE = os.path.expanduser("~/.nimbus")

if __name__ == '__main__':
    setup.logger()
    log = logging.getLogger()
    
    global data
    data = setup.client(Conf)
    log.info(str(data))
