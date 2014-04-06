import dropboxops
import driveops

BACKENDS = {
    'dropbox': {'setup': dropboxops.setup,
                'fileops': dropboxops.fileops()},
    'drive': {'setup': driveops.setup,
              'fileops': driveops.fileops()}
}
