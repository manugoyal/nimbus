import logging
import dropbox
import requests

import conf

def setup(name, conn):
    """Obtains dropbox authorization if we don't already have it"""

    log = logging.getLogger(conf.LOGGER)
    res = conn.query("SELECT token from accounts WHERE name=%s", name)
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
        flow = dropbox.client.DropboxOAuth2FlowNoRedirect(conf.DROPBOX_APP_KEY, conf.DROPBOX_APP_SECRET)
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
        conn.execute(
            "INSERT INTO accounts VALUES (%s, %s) ON DUPLICATE KEY UPDATE token=%s",
            name, token, token)

    client = dropbox.client.DropboxClient(token)

    def has_space(size):
        """Returns true if dropbox has >= size space"""
        space = client.account_info()['quota_info']['quota']
        return (space >= size)

    return token, has_space

def get_client():
    log = logging.getLogger(conf.LOGGER)
    r = requests.get('http://%s:%s/getToken/dropbox' %
                     (conf.SERVER_HOST, conf.SERVER_PORT))
    rjson = r.json()
    if 'token' not in rjson:
        log.warning("No token for dropbox backend")
        return None
    else:
        return dropbox.client.DropboxClient(rjson['token'])

def put_file(path, filePath):
    client = get_client()
    fileObj = open(filePath, 'rb')
    if client is not None:
        return client.put_file(path, fileObj, overwrite=True)

def create_folder(path):
    client = get_client()
    if client is not None:
        return client.file_create_folder(path)

def delete(path):
    client = get_client()
    if client is not None:
        return client.file_delete(path)

def move(srcpath, dstpath, isdir):
    client = get_client()
    if client is not None:
        return client.file_move(srcpath, dstpath)

def get_file(path):
    client = get_client()
    if client is not None:
        return client.get_file(path).read()

def fileops():
    return {'put_file': put_file,
            'get_file': get_file,
            'create_folder': create_folder,
            'delete': delete,
            'move': move}
