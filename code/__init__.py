import os

from flask import Flask

DB_NAME = "database.db"
UPLOAD_FOLDER = "uploads/"

# maximum size of the uploaded CSV file (MiB)
MAX_FILE_SIZE_LIMIT = 5

def _makeFolder(path: str, permissions: int) -> None:
    """Helper procedure to create a folder that may or may not already exist."""
    try:
        os.makedirs(path, mode=permissions)
    except OSError:
        pass

def create_app():
    main = Flask(__name__)

    dbPath = os.path.join(main.instance_path, DB_NAME)
    uploadPath = os.path.join(main.instance_path, UPLOAD_FOLDER)

    # TODO: make sure we securely generate these -- maybe environment variable?
    main.secret_key = b'_5#y2L"F4Q8z\n\xec]/'
    main.config.from_mapping(
        SECRET_KEY = "TODO",
        DATABASE = dbPath,
        UPLOAD_FOLDER = uploadPath,
        MAX_CONTENT_LENGTH = MAX_FILE_SIZE_LIMIT * 1024 * 1024,
        )

    # create all the relevant folders (note permissions!)
    _makeFolder(main.instance_path, permissions=740)
    _makeFolder(dbPath, permissions=640)
    _makeFolder(uploadPath, permissions=640)
        
    from . import db
    db.init_app(main)
    return main
