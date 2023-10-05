from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from geopy.distance import geodesic
from sqlalchemy import PickleType
from flask_migrate import Migrate

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smart_parking.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Model Definitions
class Emission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    co2 = db.Column(db.Float, nullable=False)
    nox = db.Column(db.Float, nullable=False)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False)

class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    residence_location = db.Column(PickleType, nullable=False)
    current_location = db.Column(PickleType, nullable=False)
    emission = db.relationship('Emission', backref='car', uselist=False)

class CarPricing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False)
    pricing_id = db.Column(db.Integer, db.ForeignKey('pricing.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)

class Pricing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parking_space_id = db.Column(db.Integer, db.ForeignKey('parking_space.id'), nullable=False)
    car_pricing = db.relationship('CarPricing', backref='pricing', lazy=True)

class ParkingSpace(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(PickleType, nullable=False)
    status = db.Column(db.Boolean, nullable=False, default=True)  # True: available, False: not available
    pricing = db.relationship('Pricing', backref='parking_space', uselist=False)

    @property
    def serialize(self):
        return {
            'id': self.id,
            'location': self.location,
            'status': 'available' if self.status else 'not available',
            'price': self.pricing.price if self.pricing else None
        }

# Helper Functions
def calculate_distance(coord1, coord2):
    return geodesic(coord1, coord2).km

def calculate_price(parking_space, car):
    base_price = 10.0  # set a base price
    price = base_price

    # Check availability
    if not parking_space.status:
        print(f"Parking space {parking_space.id} is not available.")
        return None  # or some indicator that the spot is not available

    # Distance from car to parking spot
    car_to_spot_distance = calculate_distance(car.current_location, parking_space.location)
    print(f"Distance from car to spot: {car_to_spot_distance}")
    if car_to_spot_distance < 2.0:  # within 2km
        price -= 2.0  # discount

    # Distance from car owner's residence to parking spot
    residence_to_spot_distance = calculate_distance(car.residence_location, parking_space.location)
    if residence_to_spot_distance < 2.0:  # within 2km
        price -= 2.0  # discount

    # Emission factors
    price += (car.emission.co2 + car.emission.nox) * 0.1  # updated emission pricing factor

    print(f"Final price: {price}")
    return price

# Route Definitions
@app.route('/api/v1/parking-spaces', methods=['GET'])
def get_parking_spaces():
    car_id = request.args.get('car_id')
    car = Car.query.get(car_id)
    if not car:
        return jsonify({'error': 'Car not found'}), 404

    parking_spaces = ParkingSpace.query.filter_by(status=True).all()
    result = []
    for space in parking_spaces:
        price = calculate_price(space, car)
        result.append({
            'id': space.id,
            'location': space.location,
            'status': 'available',
            'price': price
        })
    return jsonify(result)

#adding a parking spot
@app.route('/api/v1/parking-spaces', methods=['POST'])
def add_parking_space():
    data = request.get_json()
    new_space = ParkingSpace(
        location=data['location'],
        status=data.get('status', True)  # Default to True (available) if status is not provided
    )
    db.session.add(new_space)
    db.session.commit()

    return jsonify(new_space.serialize), 201


@app.route('/api/v1/parking-spaces/<int:space_id>/status', methods=['POST'])
def update_parking_space_status(space_id):
    data = request.get_json()
    parking_space = ParkingSpace.query.get(space_id)
    if not parking_space:
        return jsonify({'error': 'Parking space not found'}), 404

    status = data.get('status')
    if status is None:
        return jsonify({'error': 'No status provided'}), 400

    parking_space.status = status
    db.session.commit()

    return jsonify(parking_space.serialize), 200

@app.route('/api/v1/cars', methods=['GET'])
def get_cars():
    cars = Car.query.all()
    return jsonify([{
        'id': car.id,
        'co2_emission': car.emission.co2,  # Accessing emissions via relationship
        'nox_emission': car.emission.nox,  # Accessing emissions via relationship
        'residence_location': car.residence_location,
        'current_location': car.current_location
    } for car in cars])


@app.route('/api/v1/cars', methods=['POST'])
def add_car():
    data = request.get_json()
    new_car = Car(
        residence_location=data['residence_location'],
        current_location=data['current_location']
    )
    new_emission = Emission(
        co2=data['emission']['co2'],
        nox=data['emission']['nox'],
        car=new_car  # associate the new emission with the new car
    )
    db.session.add(new_car)
    db.session.add(new_emission)
    db.session.commit()
    return jsonify({'id': new_car.id}), 201

with app.app_context():
    # Create the database and the database table
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
