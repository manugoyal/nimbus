import torndb
import logging
import dropbox
from warnings import filterwarnings, resetwarnings
import os.path
import json

def logger():
    """Sets up the root logger to log to the console"""
    log = logging.getLogger()
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    ch.setFormatter(formatter)
    log.setLevel(logging.DEBUG)
    log.addHandler(ch)

def database(args, Conf):
    """Creates the database schema"""
    conn = torndb.Connection(Conf.HOST, '', Conf.USER)

    commands = [
        'CREATE DATABASE IF NOT EXISTS %s' % Conf.DB,
        'use %s' % Conf.DB,
        'CREATE TABLE IF NOT EXISTS accounts(name varchar(255), token varchar(255), primary key (name))'
    ]
    if args.refresh_schema:
        commands.insert(0, 'DROP DATABASE IF EXISTS %s' % Conf.DB)

    # Don't display warnings
    filterwarnings('ignore')
    for line in commands:
        conn.execute(line)
    resetwarnings()

    return conn

def _dropbox(name, data, Conf):
    """Obtains dropbox authorization if we don't already have it"""

    log = logging.getLogger()
    res = data['conn'].query("SELECT token from accounts WHERE name=%s", name)
    token = None
    changed = True

    def check_token(token):
        """Makes sure the given token is actually valid"""
        try:
            dropbox.client.DropboxClient(token).account_info()
            return True
        except dropbox.rest.ErrorResponse:
            log.error("Token %s is not a valid dropbox token" % token)
            return False

    if len(res) == 1 and check_token(res[0].token):
        changed = False
        token = res[0].token

    while token is None:
        log.info("Fetching a new dropbox token")
        flow = dropbox.client.DropboxOAuth2FlowNoRedirect(Conf.APP_KEY, Conf.APP_SECRET)
        authorize_url = flow.start()
        print '1. Go to: ' + authorize_url
        print '2. Click "Allow" (you might have to log in first)'
        print '3. Copy the authorization code.'
        code = raw_input("Enter the authorization code here: ").strip()

        try:
            token, user_id = flow.finish(code)
            if not check_token(token):
                token = None
        except dropbox.rest.ErrorResponse:
            log.error("Invalid code %s" % code)
            
            

    if changed:
        data['conn'].execute(
            "INSERT INTO accounts VALUES (%s, %s) ON DUPLICATE KEY UPDATE token=%s",
            name, token, token)

def backends(data, Conf):
    """Obtains authentication for any backend services that don't already
    have something"""

    BACKENDS = {'dropbox': _dropbox}

    for (name, func) in BACKENDS.iteritems():
        func(name, data, Conf)

def client(Conf):
    """Gets the configuration info from the file"""

    log = logging.getLogger()
    if os.path.exists(Conf.FILE):
        try:
            data = json.loads(open(Conf.FILE, 'r').read())
            return data
        except:
            log.error("Nimbus configuration file %s is corrupt! Please create a correct one and restart the client")
            raise
    else:
        log.error("Please create a nimbus configuration file at %s and restart the client" % Conf.FILE)
        raise Exception("No configuration file at %s" % Conf.FILE)
