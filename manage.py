import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app, socketio

app = create_app(os.getenv('FLASK_CONFIG') or 'default')

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=5001,
        debug=False,
        use_reloader=False,
    )
