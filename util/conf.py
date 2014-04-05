import os.path

# Server constants
HOST = '127.0.0.1'
DB = 'nimbus'
USER = 'root'
DROPBOX_APP_KEY = ''
DROPBOX_APP_SECRET = ''
DRIVE_CLIENT_ID = ''
DRIVE_CLIENT_SECRET = ''
DRIVE_OAUTH_SCOPE = 'https://www.googleapis.com/auth/drive'
DRIVE_REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 8000

# Client constants
CONF_FILE = os.path.expanduser("~/.nimbus")
MAX_EVENTS = 100

# Common constants
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
LOGGER = 'nimbus'
