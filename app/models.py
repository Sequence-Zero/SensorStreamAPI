from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db

def utcnow():
    return datetime.now(timezone.utc)

class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.String(36), primary_key=True)  # UUID string
    name = db.Column(db.String(120), nullable=False)
    api_key_hash = db.Column(db.String(255), nullable=False) #stores a hashed key, not plaintext
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False) #timestamp for readings
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=True) #devices last seen

    def set_api_key(self, raw_key: str) -> None: #hashes the raw key
        self.api_key_hash = generate_password_hash(raw_key) 

    def check_api_key(self, raw_key: str) -> bool: 
        return check_password_hash(self.api_key_hash, raw_key) #checks for match

class Reading(db.Model): 
    __tablename__ = "readings" 
    #one row per sensor sample
    id = db.Column(db.Integer, primary_key=True, autoincrement=True) #set to UUID primary key
    device_id = db.Column(db.String(36), db.ForeignKey("devices.id"), nullable=False, index=True)

    sensor = db.Column(db.String(40), nullable=False, index=True)  #imu_ax, emg_ch1
    ts = db.Column(db.DateTime(timezone=True), nullable=False, index=True) #timestamp reading
    value = db.Column(db.Float, nullable=False) #stores sensor value

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False) 

    __table_args__ = (
        db.Index("ix_device_sensor_ts", "device_id", "sensor", "ts"),
    )

    #File is the database schema
    #Time series DB aka just rows with timestamps + good indexes
    #Device class + Reading class
    #Device class has id, name, api key hash, created at time stamp, and last seen at

    #Reading class has id, device id, sensor, time stamp, value for the reading, and a created at
    #time stamp