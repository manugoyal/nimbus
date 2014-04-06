import logging
import httplib2
import pprint

from apiclient.discovery import build
from apiclient.http import MediaFileUpload
from oauth2client.client import OAuth2WebServerFlow

import pickle
import conf
import requests
import time

def setup(name, conn):
    """Obtains google drive authorization if we don't already have it"""

    log = logging.getLogger(conf.LOGGER)
    res = conn.query("SELECT token from accounts WHERE name=%s", name)

    token = None
    if len(res) == 1:
        tokenstr = str(res[0].token)
        token = pickle.loads(tokenstr)
    else:
        while token is None:
            log.info("Fetching a new drive token")
            flow = OAuth2WebServerFlow(conf.DRIVE_CLIENT_ID,
                                       conf.DRIVE_CLIENT_SECRET,
                                       conf.DRIVE_OAUTH_SCOPE,
                                       conf.DRIVE_REDIRECT_URI)
            authorize_url = flow.step1_get_authorize_url()
            print '1. Go to: ' + authorize_url
            print '2. Click "Allow" (you might have to log in first)'
            print '3. Copy the authorization code.'
            code = raw_input("Enter the authorization code here: ").strip()
            token = flow.step2_exchange(code)
        tokenstr = pickle.dumps(token)
        conn.execute('INSERT INTO accounts VALUES (%s, %s) ON DUPLICATE KEY UPDATE token=%s',
                     name, tokenstr, tokenstr)

    http = httplib2.Http()
    token.authorize(http)
    client = build('drive', 'v2', http=http)

    def has_space(size):
        """Returns true if drive has >= size space"""
        space = client.about().get().execute()['quotaBytesTotal']
        return (space >= size)

    return tokenstr, has_space

def get_client():
    log = logging.getLogger(conf.LOGGER)
    for i in range(5):
        try:
            r = requests.get('http://%s:%s/getToken/drive' %
                             (conf.SERVER_HOST, conf.SERVER_PORT)) 
            rjson = r.json()
            break
        except:
            time.sleep(1)

    if 'token' not in rjson:
        log.warning("No token for drive backend")
        return None
    else:
        http = httplib2.Http()
        token = pickle.loads(str(rjson['token']))
        token.authorize(http)
        return build('drive', 'v2', http=http)

def get_drivefile(title, client):
    """Returns the file object of the drive file with the given title"""
    params = {'q': 'title = "%s" and trashed = false' % title}
    files = client.files().list(**params).execute()
    if len(files['items']) == 0:
        return None
    else:
        return files['items'][0]

def put_file(path, filePath):
    try:
        client = get_client()
        media_body = MediaFileUpload(filePath, mimetype='text/plain', resumable=False)
        f = get_drivefile(path, client)
        if f is not None:
            client.files().update(fileId=f['id'], media_body=media_body).execute()
        else:
            body = {'title': path, 'description': path, 'mimeType': 'text/plain'}
            client.files().insert(body=body, media_body=media_body).execute()
    except Exception, e:
        logging.getLogger(conf.LOGGER).error(str(e))

def create_folder(path):
    # Drive isn't good at folders
    return

def delete(path):
    client = get_client()
    if client is not None:
        f = get_drivefile(path, client)
        client.files().delete(fileId=f['id']).execute()

def move(srcpath, dstpath, isdir):
    if not isdir:
        client = get_client()
        if client is not None:
            f = get_drivefile(srcpath, client)
            body = {'title': dstpath, 'description': dstpath, 'mimeType': 'text/plain'}
            client.files().update(fileId=f['id'], body=body).execute()

def get_file(path):
    client = get_client()
    if client is not None:
        f = get_drivefile(path, client)
        download_url = f.get('downloadUrl')
        if download_url:
            resp, content = client._http.request(download_url)
            if resp.status == 200:
                return content
        return None

def get_link(path, tokenstr):
    http = httplib2.Http()
    token = pickle.loads(str(tokenstr))
    token.authorize(http)
    client = build('drive', 'v2', http=http)
    f = get_drivefile(path, client)
    return f.get('alternateLink')

def fileops():
    return {'put_file': put_file,
            'get_file': get_file,
            'create_folder': create_folder,
            'delete': delete,
            'move': move,
            'get_link': get_link}
