import os

from app import create_app #imports the app factory from __init__
from dotenv import load_dotenv
load_dotenv()
app = create_app() #constructs a configured Flask app with routes and DB ready
port = int(os.getenv("PORT", 5000))

if __name__ == "__main__": 
    app.run(host="0.0.0.0", port=port, debug=False) #starts the app using the host/port Render expects
    
