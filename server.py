import logging
import argparse
from util import setup

class Conf:
    HOST = '127.0.0.1'
    DB = 'nimbus'
    USER = 'root'
    APP_KEY = '4eoz7ay95gge8yb'
    APP_SECRET = '3do936xg7vr8bnj'

if __name__ == '__main__':
    setup.logger()

    parser = argparse.ArgumentParser(description=
                                     'A cloud storage unification service')
    parser.add_argument('-refresh-schema', action='store_true', 
                        help='Recreate the database schema from scratch')
    args = parser.parse_args()
    log = logging.getLogger()

    log.info('Setting up the database schema')
    global data
    data = dict(conn=setup.database(args, Conf))

    log.info('Setting up backends')
    setup.backends(data, Conf)

