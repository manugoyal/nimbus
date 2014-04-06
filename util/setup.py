import torndb
import logging
import dropbox
from warnings import filterwarnings, resetwarnings
import os.path
import pickle
import requests
from datetime import datetime

import conf
import backends

def logger():
    """Sets up the root logger to log to the console"""
    log = logging.getLogger(conf.LOGGER)
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    ch.setFormatter(formatter)
    log.setLevel(logging.DEBUG)
    log.addHandler(ch)

def get_connection():
    return torndb.Connection(conf.HOST, conf.DB, conf.USER)

def database(args, data):
    """Creates the database schema, storing the connection in the data
    dict"""
    conn = torndb.Connection(conf.HOST, '', conf.USER)

    commands = [
        'CREATE DATABASE IF NOT EXISTS %s' % conf.DB,

        'use %s' % conf.DB,

        'CREATE TABLE IF NOT EXISTS accounts(name VARCHAR(255)'
        'PRIMARY KEY NOT NULL, token varchar(255) NOT NULL)',

        'CREATE TABLE IF NOT EXISTS uid(id INT PRIMARY KEY NOT NULL)',

        'CREATE TABLE IF NOT EXISTS filesystem(uid INT NOT NULL,'
        'path VARCHAR(255) NOT NULL, backend VARCHAR(255) NOT NULL,'
        'PRIMARY KEY(uid, path))',

        'CREATE TABLE IF NOT EXISTS log(id INT PRIMARY KEY AUTO_INCREMENT,'
        'uid INT NOT NULL, content VARCHAR(255) NOT NULL, time DATETIME NOT NULL)'
    ]
    if args.refresh_schema:
        commands.insert(0, 'DROP DATABASE IF EXISTS %s' % conf.DB)

    # Don't display warnings
    filterwarnings('ignore')
    for line in commands:
        conn.execute(line)

    resetwarnings()

def backend(data):
    """Obtains authentication for any backend services that don't already
    have something, storing the authentication in the data dict
    
    """

    conn = get_connection()
    data['backends'] = {}

    for name in backends.BACKENDS:
        token, has_space = backends.BACKENDS[name]['setup'](name, conn)
        data['backends'][name] = {'token': token,
                                  'has_space': has_space}

def client(base_path):
    """Gets the configuration info from the configuration file"""

    log = logging.getLogger(conf.LOGGER)
    conf_data = {}
    if os.path.exists(conf.CONF_FILE):
        try:
            conf_data = pickle.load(open(conf.CONF_FILE, 'r'))
        except:
            log.error("Nimbus configuration file %s is corrupt!"
                      "Please delete it and restart the client" % 
                      conf.CONF_FILE)
            raise

    if base_path not in conf_data:
        conf_data[base_path] = {}
    path_data = conf_data[base_path]

    if 'uid' not in path_data:
        r = requests.get('http://%s:%s/newUID' % (conf.SERVER_HOST, conf.SERVER_PORT))
        path_data['uid'] = r.json()['uid']
    if 'last_pull' not in path_data:
        path_data['last_pull'] = datetime.utcfromtimestamp(0).strftime(conf.DATETIME_FORMAT)
    if 'snapshot' not in path_data:
        path_data['snapshot'] = None

    return path_data

def write_path_data(path_data, base_path):
    """Writes the updated configuration info for the client"""
    if os.path.exists(conf.CONF_FILE):
        cf = open(conf.CONF_FILE, 'r')
        conf_data = pickle.load(cf)
    else:
        conf_data = {}

    conf_data[base_path] = path_data

    cf = open(conf.CONF_FILE, 'w')
    pickle.dump(conf_data, cf)
    cf.close()

