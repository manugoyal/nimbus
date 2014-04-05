import logging
import argparse
from util import setup, conf, backends
from flask import Flask, request, send_from_directory
import pickle
import json
from datetime import datetime
import threading
import random
import os.path
import os

app = Flask(__name__)
web_files = os.path.join(os.getcwd(), 'web')
transaction_lock = threading.Lock()

@app.route('/newUID', methods=['GET'])
def newUID():
    """Returns the UID in the table and increments it"""
    conn = setup.get_connection()
    res = conn.query("SELECT id FROM uid LIMIT 1")
    print res
    if len(res) == 0:
        conn.execute("INSERT INTO uid VALUES (0)")
        retuid = 0
    else:
        retuid = res[0].id

    conn.execute("UPDATE uid SET id=id+1")
    return json.dumps({'uid': retuid})

@app.route('/getToken/<backend>', methods=['GET'])
def getToken(backend):
    """Returns the token associated with the given backend"""
    conn = setup.get_connection()
    res = conn.query("SELECT token FROM accounts WHERE name=%s",
                     backend)
    if len(res) == 0:
        log.warning("No backend with name %s found" % backend)
        return json.dumps({})
    else:
        return json.dumps({'token': res[0].token})

@app.route('/postEvents', methods=['POST'])
def postEvents():
    """Deals with a series of filesystem events from a client"""
    log = logging.getLogger(conf.LOGGER)
    conn = setup.get_connection()
    uid = int(request.form['uid'])
    events = json.loads(request.form['events'])
    utcnow = datetime.utcnow()
    utcstr = utcnow.strftime(conf.DATETIME_FORMAT)

    try:
        client_ops = []

        backend_query = 'SELECT backend FROM filesystem WHERE path=%s'
        file_not_found = lambda path, op: "Couldn't find file %s to %s" % (path, op)

        for e in events:
            # The database logging will be done after the conditional block
            if e['type'] == 'created':
                # Picks a random backend
                backend = random.choice([b for b in data['backends']])
                # # Searches for a backend with enough space 
                # backend = None
                # for b in data['backends']:
                #     if data['backends'][b]['has_space'](e['size']):
                #         backend = b
                # if backend is None:
                #     log.warning("Not enough space to create file %s of size %s." % (e['path'], e['size']))
                #     continue
                conn.execute('INSERT INTO filesystem VALUES (%s, %s)',
                             e['path'], backend)
                # The log needs to also contain the backend, so
                # clients can know where to fetch the file from
                e['backend'] = backend

            elif e['type'] == 'deleted':
                backend = conn.query(backend_query, e['path'])
                if len(backend) == 0:
                    log.warning(file_not_found("delete", e['path']))
                    continue
                conn.execute('DELETE FROM filesystem WHERE path=%s', e['path'])
                e['backend'] = backend[0].backend

            elif e['type'] == 'modified':
                backend = conn.query(backend_query, e['path'])
                if len(backend) == 0:
                    log.warning(file_not_found("modify", e['path']))
                    continue
                e['backend'] = backend[0].backend

            elif e['type'] == 'moved':
                backend = conn.query(backend_query, e['path'])
                if len(backend) == 0:
                    log.warning(file_not_found("rename", e['path']))
                    continue
                conn.execute('UPDATE filesystem SET path=%s WHERE path=%s',
                                     e['dstpath'], e['path'])
                e['backend'] = backend[0].backend
            else:
                log.error("Encountered unknown watchdog event %s" % e['type'])
                continue

            # Does the logging with the modified event
            client_ops.append(e)

        # We'll release the transaction lock once the client completes its
        # operations
        return json.dumps({'client_ops': client_ops, 'utcstr': utcstr})
    except Exception, e:
        log.error(str(e))
        return json.dumps({'client_ops': [], 'utcstr': utcstr})

@app.route('/completePost', methods=['POST'])
def completePost():
    """Logs the events in the database

    """
    log.debug(request.form)
    uid = int(request.form['uid'])
    utcstr = request.form['utcstr']
    events = json.loads(request.form['events'])
    conn = setup.get_connection()
    log.debug(uid)
    log.debug(utcstr)
    log.debug(events)
    transaction_lock.acquire(True)
    try:
        for e in events:
            log.debug(json.dumps(e))
            conn.execute('INSERT INTO log(uid, content, time) VALUES (%s, %s, %s)',
                         uid, json.dumps(e), utcstr)
    except Exception, e:
        log.error(str(e))
    finally:
        transaction_lock.release()

@app.route('/fetchLog', methods=['GET'])
def fetchLog():
    """Returns all log events that aren't from the given uid since the
    given time. Also returns the current server time for the next
    pull.

    """
    log = logging.getLogger(conf.LOGGER)
    conn = setup.get_connection()
    uid = int(request.args.get('uid'))
    last_pull = int(request.args.get('last_pull'))

    # We have to take the transaction_lock, since we're reading from
    # the log.
    transaction_lock.acquire(True)
    try:
        utcstr = datetime.utcnow().strftime(conf.DATETIME_FORMAT)
        retevents = conn.query('SELECT id, content FROM log WHERE uid != %s AND id > %s',
                               uid, last_pull)
        events = []
        lastid = last_pull
        for e in retevents:
            events.append(e.content)
            lastid = e.id

        return json.dumps({'events': events, 'last_id': lastid})
    except Exception, e:
        log.error(str(e))
    finally:
        pass
        transaction_lock.release()

@app.route('/fetchTree', methods=['GET'])
def fetchTree():
    """Turns the files in filesystem into a tree. Used for the javascript
    client.

    """
    conn = setup.get_connection()
    files = conn.query('SELECT path FROM filesystem')

    tree = {}
    def add_path(tree, path):
        dirs = path.split(os.sep)
        inner = tree
        for d in dirs:
            if d not in inner:
                inner[d] = {}
            inner = inner[d]

    def add_pathname(tree, path):
        dirs = path.split(os.sep)
        inner1 = tree
        inner2 = inner1
        for d in dirs:
            inner1 = inner2
            inner2 = inner2[d]
        if inner1[dirs[-1]] == {}:
            inner1[dirs[-1]] = path

    for f in files:
        add_path(tree, f.path)
    for f in files:
        add_pathname(tree, f.path)

    return json.dumps(tree)

@app.route('/fetchFile', methods=['GET'])
def fetchFile():
    """Returns a link for the specified file."""
    path = request.args.keys()[0]
    print path
    conn = setup.get_connection()
    f = conn.query('SELECT backend FROM filesystem WHERE path=%s', path)
    if len(f) == 0:
        link = ''
    else:
        backend = f[0].backend
        link = backends.BACKENDS[backend]['fileops']['get_link'] (path, data['backends'][backend]['token'])
    return json.dumps({'link': link})


@app.route('/', methods=['GET'])
def root():
    return send_from_directory(web_files, 'index.html')

@app.route('/js/<filename>', methods=['GET'])
def js(filename):
    return send_from_directory(web_files, filename)

if __name__ == '__main__':
    setup.logger()

    parser = argparse.ArgumentParser(description=
                                     'A cloud storage unification service')
    parser.add_argument('-refresh-schema', action='store_true',
                        help='Recreate the database schema from scratch')
    args = parser.parse_args()
    log = logging.getLogger(conf.LOGGER)

    log.info('Setting up the database schema')
    global data
    data = {}
    setup.database(args, data)

    log.info('Setting up backends')
    setup.backend(data)

    log.info('Starting the server')
    app.run(port=conf.SERVER_PORT)
