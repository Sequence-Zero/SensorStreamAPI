from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy() #creates thge SQLAlchemy ORM manager

#models imports db, routes import db, app factory initializes it once