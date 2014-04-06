import dropboxops

BACKENDS = {'dropbox': 
            {'setup': dropboxops.setup,
             'fileops': dropboxops.fileops()}
        }
