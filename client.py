import logging
import signal
import os.path
from util import conf, setup, backends
import time
import sys
import argparse
import requests
import json
import os
import stat
import traceback
import shutil

from watchdog.utils import dirsnapshot

def create_snapshot_diff(path_data, base_path):
    """Snapshots the base_path folder and diff it with the current
    snapshot to create a list of modifications to the file system,
    which it returns.

    """

    def resolve(path):
        """Resolves the given path against the configuration path"""
        return os.path.relpath(path, base_path)

    ds = dirsnapshot.DirectorySnapshot(base_path, True)
    # We separate directory events and file events, and in the end
    # combine them, putting the directory events first
    direvents = []
    fileevents = []
    if path_data['snapshot'] is None:
        # We make create events for all the items in the snapshot,
        for path in ds.paths:
            stinfo = ds.stat_info(path)
            item = dict(type='created',
                        path=resolve(path),
                        isdir=stat.S_ISDIR(stinfo.st_mode),
                        size=stinfo.st_size)
            if item['isdir']:
                direvents.append(item)
            else:
                fileevents.append(item)
    else:
        # Diff this snapshot with the original snapshot and create
        # events out of that
        diff = dirsnapshot.DirectorySnapshotDiff(path_data['snapshot'], ds)
        for dd in diff.dirs_deleted:
            direvents.append(dict(type='deleted', path=resolve(dd), isdir=True))
        for dc in diff.dirs_created:
            direvents.append(dict(type='created', path=resolve(dc),
                                  isdir=True, size=ds.stat_info(dc).st_size))
        # We don't care about modified directories
        for dm in diff.dirs_moved:
            direvents.append(dict(type='moved', path=resolve(dm[0]),
                                  dstpath=resolve(dm[1]), isdir=True))
        for fd in diff.files_deleted:
            fileevents.append(dict(type='deleted', path=resolve(fd), isdir=False))
        for fc in diff.files_created:
            fileevents.append(dict(type='created', path=resolve(fc),
                                   isdir=False, size=ds.stat_info(fc).st_size))
        for fm in diff.files_modified:
            # We only consider files modified if the size or mode is
            # different
            pdinfo = path_data['snapshot'].stat_info(fm)
            dsinfo = ds.stat_info(fm)
            if pdinfo.st_mode != dsinfo.st_mode or pdinfo.st_size != dsinfo.st_size:
                fileevents.append(dict(type='modified', path=resolve(fm), isdir=False))
        for fm in diff.files_moved:
            fileevents.append(dict(type='moved', path=resolve(fm[0]),
                                   dstpath=resolve(fm[1]), isdir=False))

    # We remove direvents with path="."
    direvents = [de for de in direvents if de['path'] != '.']
    # Store the latest snapshot and return the events
    path_data['snapshot'] = ds
    return direvents + fileevents

def server_sender(path_data, base_path, events):
    """Polls the global queue for events and sends them to the server to
    figure out what to do about them. Returns the poll time from the server

    """

    log = logging.getLogger(conf.LOGGER)
    log.info(events)

    r = requests.post('http://%s:%s/postEvents' %
                      (conf.SERVER_HOST, conf.SERVER_PORT),
                      data={'uid': path_data['uid'],
                            'events': json.dumps(events)})
    try:
        client_ops = r.json()['client_ops']
        utcstr = r.json()['utcstr']

        log.info('CLIENT_OPS: ' + str(client_ops))

        # Executes the returned client operations.
        log.info("Executing client cloud operations")
        def fs_path(e):
            return os.path.join(base_path, e['path'])

        for e in client_ops:
            fileops = backends.BACKENDS[e['backend']]['fileops']
            if e['type'] == 'created':
                if e['isdir']:
                    fileops['create_folder'](e['path'])
                else:
                    fileops['put_file'](e['path'], fs_path(e))
            elif e['type'] == 'deleted':
                fileops['delete'](e['path'])
            elif e['type'] == 'modified':
                fileops['put_file'](e['path'], fs_path(e))
            elif e['type'] == 'moved':
                fileops['move'](e['path'], e['dstpath'], e['isdir'])
            else:
                log.error("Unknown op type %s" % e['type'])
    except Exception, e:
        _, _, exec_traceback = sys.exc_info()
        traceback.print_tb(exec_traceback, limit=1, file=sys.stdout)
        log.error(str(e))
    finally:
        requests.post('http://%s:%s/completePost' %
                      (conf.SERVER_HOST, conf.SERVER_PORT),
                      data={'uid': path_data['uid'],
                            'events': json.dumps(client_ops),
                            'utcstr': utcstr})

def server_poller(path_data, base_path):
    """Polls the server log for changes due to other clients and replays
    those changes. Then takes a snapshot of the changed directory.

    """
    r = requests.get('http://%s:%s/fetchLog' %
                     (conf.SERVER_HOST, conf.SERVER_PORT),
                     params={'uid': path_data['uid'],
                             'last_pull': path_data['last_pull']})
    rjson = r.json()
    path_data['last_pull'] = rjson['last_id']
    replayevents = rjson['events']

    try:
        # Executes the returned log operations
        log.info("Executing fetched log operations, from %d" % path_data['last_pull'])
        def fs_path(path):
            return os.path.join(base_path, path)

        for re in replayevents:
            try:
                e = json.loads(re)
                log.debug(e)
                fileops = backends.BACKENDS[e['backend']]['fileops']
                if e['type'] == 'created':
                    if e['isdir']:
                        os.makedirs(fs_path(e['path']))
                    else:
                        fspath = fs_path(e['path'])
                        # Create the directories up to fspath
                        try:
                            os.makedirs(os.path.dirname(fspath))
                        except:
                            pass
                        with open(fspath, 'wb') as out:
                            fcontent = fileops['get_file'](e['path'])
                            out.write(fcontent)
                elif e['type'] == 'deleted':
                    if e['isdir']:
                        shutil.rmtree(fs_path(e['path']))
                    else:
                        os.remove(fs_path(e['path']))
                elif e['type'] == 'modified':
                    with open(fs_path(e['path']), 'wb') as out:
                        fcontent = fileops['get_file'](e['path'])
                        out.write(fcontent)
                elif e['type'] == 'moved':
                    srcpath, dstpath = fs_path(e['path']), fs_path(e['dstpath'])
                    if os.path.exists(dstpath):
                        # We're going to assume e['path'] is a parent
                        # directory or something, that has already
                        # been created, so we'll just delete e['path']
                        if os.path.isdir(srcpath):
                            os.rmdir(srcpath)
                        else:
                            os.remove(srcpath)
                    else:
                        # Create the directories up to dstpath
                        try:
                            os.makedirs(os.path.dirname(dstpath))
                        except:
                            pass
                        shutil.move(srcpath, dstpath)
                else:
                    log.error("Unknown op type %s" % e['type'])
            except Exception, e:
                log.warning(str(e))

    except Exception, e:
        _, _, exec_traceback = sys.exc_info()
        traceback.print_tb(exec_traceback, limit=1, file=sys.stdout)
        log.error(str(e))


    path_data['snapshot'] = dirsnapshot.DirectorySnapshot(base_path, True)

if __name__ == '__main__':
    setup.logger()
    log = logging.getLogger(conf.LOGGER)

    parser = argparse.ArgumentParser(description='A cloud storage unification service')
    parser.add_argument('-path', default='',
                        help="The path of the folder to look at")
    args = parser.parse_args()
    base_path = os.path.normpath(args.path)

    path_data = setup.client(base_path)

    def signal_handler(signum, frame):
        """A signal handler that cleans up upon receiving an interrupt"""
        log.info("Stopping the watchdog observer")

        log.info("Writing path_data to configuration")
        setup.write_path_data(path_data, base_path)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    while True:
        time.sleep(3)
        events = create_snapshot_diff(path_data, base_path)
        server_sender(path_data, base_path, events)
        server_poller(path_data, base_path)
