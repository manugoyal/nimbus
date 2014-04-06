import logging
import argparse
from util import setup, conf
from flask import Flask, request
import pickle
import json
from datetime import datetime
import threading

app = Flask(__name__)
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

    # We now proceed with the transaction. For simplicity, concurrent
    # transactions are serialized with transaction_lock. We
    # simultaneously modify the databases's filesystem representation
    # and log events. Since the client needs to actually do the cloud
    # operations, we don't release the transaction lock when we're
    # done with this function. Instead, we return a list of operations
    # for the client and wait for it to respond, then release the lock.
    transaction_lock.acquire(True)
    try:
        client_ops = []

        backend_query = 'SELECT backend FROM filesystem WHERE uid=%s AND path=%s'
        file_not_found = lambda uid, path, op: "Couldn't find file (%s, %s) to %s" % (uid, path, op)

        for e in events:
            # The database logging will be done after the conditional block
            if e['type'] == 'created':
                # Searches for a backend with enough space
                backend = None
                for b in data['backends']:
                    if data['backends'][b]['has_space'](e['size']):
                        backend = b
                if backend is None:
                    log.warning("Not enough space to create file %s of size %s." % (e['path'], e['size']))
                    continue
                conn.execute('INSERT INTO filesystem VALUES (%s, %s, %s)',
                                     uid, e['path'], backend)
                # The log needs to also contain the backend, so
                # clients can know where to fetch the file from
                e['backend'] = backend

            elif e['type'] == 'deleted':
                backend = conn.query(backend_query, uid, e['path'])
                if len(backend) == 0:
                    log.warning(file_not_found("delete", uid, e['path']))
                    continue
                conn.execute('DELETE FROM filesystem WHERE uid=%s AND path=%s', uid, e['path'])
                e['backend'] = backend[0].backend

            elif e['type'] == 'modified':
                backend = conn.query(backend_query, uid, e['path'])
                if len(backend) == 0:
                    log.warning(file_not_found("modify", uid, e['path']))
                    continue
                e['backend'] = backend[0].backend

            elif e['type'] == 'moved':
                backend = conn.query(backend_query, uid, e['path'])
                if len(backend) == 0:
                    log.warning(file_not_found("rename", uid, e['path']))
                    continue
                conn.execute('UPDATE filesystem SET path=%s WHERE uid=%s AND path=%s',
                                     e['dstpath'], uid, e['path'])
                e['backend'] = backend[0].backend
            else:
                log.error("Encountered unknown watchdog event %s" % e['type'])
                continue

            # Does the logging with the modified event
            e['uid'] = uid
            conn.execute('INSERT INTO log(uid, content, time) VALUES (%s, %s, %s)',
                         uid, json.dumps(e), utcstr)
            client_ops.append(e)
            log.debug(e)

        # We'll release the transaction lock once the client completes its
        # operations
        return json.dumps({'client_ops': client_ops})
    except Exception, e:
        log.error(str(e))
        transaction_lock.release()
        return json.dumps({'client_ops': []})

@app.route('/completePost', methods=['POST'])
def completePost():
    """Releases the transaction lock

    """

    log = logging.getLogger(conf.LOGGER)
    log.debug("Releasing transaction lock")
    transaction_lock.release()
    return 'SUCCESS'

@app.route('/fetchLog', methods=['GET'])
def fetchLog():

    """Returns all log events that aren't from the given uid since the
    given time. Also returns the current server time for the next
    pull.

    """
    log = logging.getLogger(conf.LOGGER)
    conn = setup.get_connection()
    uid = int(request.args.get('uid'))
    last_pull = request.args.get('last_pull')

    # We have to take the transaction_lock, since we're reading from
    # the log.
    transaction_lock.acquire(True)
    try:
        utcstr = datetime.utcnow().strftime(conf.DATETIME_FORMAT)
        retevents = conn.query('SELECT content FROM log WHERE uid != %s AND time >= %s',
                               uid, last_pull)
        events = []
        for e in retevents:
            events.append(e.content)

        log.debug("Fetching log: %s" % ([events, utcstr]))
        return json.dumps({'events': events, 'pull_time': utcstr})
    except Exception, e:
        log.error(str(e))
    finally:
        transaction_lock.release()


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
