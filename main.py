import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, port=5000, host='0.0.0.0')
