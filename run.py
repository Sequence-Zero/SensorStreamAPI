from app import create_app #imports the app factory from __init__

app = create_app() #constructs a configured Flask app with routes and DB ready

if __name__ == "__main__": 
    app.run(host="127.0.0.1", port=5000, debug=True) #starts the development server on localhost atm
    