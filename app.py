from flask import Flask, render_template, request, jsonify
from datetime import datetime
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="127.0.0.1",
            port=3306,
            user="root",
            password="abdellahA2002",
            database="cnc_data",
        )
        return conn
    except Error as e:
        print("Error connecting to MySQL:", e)
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/orders')
def orders():
    return render_template('orders.html')

@app.route('/specs')
def specs():
    return render_template('specs.html')

@app.route('/add_order_to_library', methods=['POST'])
def add_order_to_library():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        data = request.get_json()
        order_number = data["orderNumber"]
        apn_id = data["apnID"]
        specification = data["specification"]
        planned_quantity = int(data["plannedQuantity"])
        directions = data.get("directions", [])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        direction_map = {
            "Top": "top",
            "Bot": "bot",
            "Front": "front",
            "Back": "back",
            "Left": "left",
            "Right": "right"
        }

        direction_values = {col: 0 for col in direction_map.values()}

        if directions:
            for d in directions:
                col = direction_map.get(d)
                if col:
                    direction_values[col] = planned_quantity

        query = """
            INSERT INTO orders_library (
                orderNum, apnID, specification, planned_quantity,
                top, bot, front, back, `left`, `right`, createdDate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        values = (
            order_number,
            apn_id,
            specification,
            planned_quantity,
            direction_values["top"],
            direction_values["bot"],
            direction_values["front"],
            direction_values["back"],
            direction_values["left"],
            direction_values["right"],
            timestamp
        )

        with conn.cursor() as cursor:
            cursor.execute(query, values)
            conn.commit()

        return jsonify({"message": "Order added to library with direction quantity fully assigned."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/all_orders', methods=['GET'])
def all_orders():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        query = """
            SELECT ol.orderNum, ol.apnID, s.name, ol.planned_quantity,
                   ol.createdDate, ol.top, ol.bot, ol.front, ol.back,
                   ol.left, ol.right
            FROM orders_library ol
            JOIN specifications s ON ol.specification = s.id
        """

        with conn.cursor() as cursor:
            cursor.execute(query)
            results = cursor.fetchall()

        data_list = []
        for row in results:
            (orderNum, apnID, specName, plannedQty, createdDate,
             top, bot, front, back, left, right) = row
            
            data_list.append({
                "orderNumber": orderNum,
                "apnID": apnID,
                "specification": specName,
                "plannedQuantity": plannedQty,
                "createdDate": createdDate.strftime("%Y-%m-%d %H:%M:%S") if hasattr(createdDate, "strftime") else str(createdDate),
                "top": top,
                "bot": bot,
                "front": front,
                "back": back,
                "left": left,
                "right": right
            })

        return jsonify({"data": data_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/production')
def production():
    return render_template('production.html')

@app.route('/production_history', methods=['GET'])
def production_history():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        query = """
            SELECT pr.order, pr.apn, s.name, pr.quantity,
                   pr.machine, pr.createdDate,
                   pr.top, pr.bot, pr.front, pr.back, pr.left, pr.right
            FROM production pr
            JOIN specifications s ON pr.specification = s.id
            ORDER BY pr.createdDate DESC
        """

        with conn.cursor() as cursor:
            cursor.execute(query)
            results = cursor.fetchall()

        data_list = []
        for row in results:
            (orderNum, apnID, specName, quantity, machine, createdDate,
             top, bot, front, back, left, right) = row

            data_list.append({
                "orderNumber": orderNum,
                "apnID": apnID,
                "specification": specName,
                "quantityProduced": quantity,
                "machine": machine,
                "dateTime": createdDate.strftime("%Y-%m-%d %H:%M:%S") if hasattr(createdDate, "strftime") else str(createdDate),
                "top": top,
                "bot": bot,
                "front": front,
                "back": back,
                "left": left,
                "right": right
            })

        return jsonify({"data": data_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/submit_production', methods=['POST'])
def submit_production():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        data = request.get_json()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        required = ["orderNumber", "apnID", "specification", "quantity", "machine"]
        missing = [f for f in required if f not in data or not str(data[f]).strip()]
        if missing:
            return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

        quantity = int(data.get("quantity", 0))
        if quantity <= 0:
            return jsonify({"error": "Quantity must be greater than 0"}), 400

        directions = data.get("directions", [])

        direction_map = {
            "Top": "top",
            "Bot": "bot",
            "Front": "front",
            "Back": "back",
            "Left": "left",
            "Right": "right"
        }

        direction_values = {col: 0 for col in direction_map.values()}

        if directions:
            for d in directions:
                col = direction_map.get(d)
                if col:
                    direction_values[col] = quantity        
        query = """
            INSERT INTO production (
                `order`, apn, specification, quantity, machine,
                top, bot, front, back, `left`, `right`, createdDate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            data["orderNumber"],
            data["apnID"],
            data["specification"],
            quantity,
            data["machine"],
            direction_values["top"],
            direction_values["bot"],
            direction_values["front"],
            direction_values["back"],
            direction_values["left"],
            direction_values["right"],
            timestamp
        )
        print(values)
        with conn.cursor() as cursor:
            cursor.execute(query, values)
            conn.commit()

        return jsonify({"message": "CNC order submitted successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/update_directions', methods=['POST'])
def update_directions():
    try:
        data = request.get_json()
        conn = get_db_connection()
        order_num = data.get('orderNumber')
        apn_id = data.get('apnID')

        if not order_num or not apn_id:
            return jsonify({"error": "Order Number and APN-ID required"}), 400
        order = None
        query = """
            SELECT * 
            FROM orders_library 
            WHERE orderNum = %s AND apnID = %s
        """
        

        with conn.cursor() as cursor:
            cursor.execute(query,(order_num,apn_id))
            order = cursor.fetchone()
        
        if not order:
            return jsonify({"error": "Order not found"}), 404
        directions = {
            "top": 0,
            "bot": 0,
            "left": 0,
            "right": 0,
            "front": 0,
            "back": 0
        }
        directions['top'] = int(data.get('top', 0))
        directions['bot'] = int(data.get('bot', 0))
        directions['left'] = int(data.get('left', 0))
        directions['right'] = int(data.get('right', 0))
        directions['front'] = int(data.get('front', 0))
        directions['back'] = int(data.get('back', 0))
        directions_list = [d for d in ['top', 'bot', 'left', 'right', 'front', 'back'] if directions[d] > 0]
        directionsString = "-".join(directions_list)

        query = """
            UPDATE orders_library SET
                top = %s, bot = %s, front = %s,
                back = %s, `left` = %s, `right` = %s,
                directions = %s
            WHERE orderNum = %s AND apnID = %s
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (directions['top'],directions['bot'],directions['front'],directions['back'] ,directions['left'] ,directions['right'], directionsString, order_num, apn_id))
            conn.commit()

        return jsonify({"message": "Directions updated successfully."})
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500
    finally:
        conn.close()

@app.route('/api/orders')
def get_orders():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        query = """
            SELECT orderNum, apnID, specification, planned_quantity
            FROM orders_library
        """
        with conn.cursor() as cursor:
            cursor.execute(query)
            results = cursor.fetchall()

        orders = []
        for row in results:
            orders.append({
                "orderNum": row[0],
                "apnID": row[1],
                "specification": row[2],
                "plannedQuantity": row[3]
            })

        return jsonify({"data": orders})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(host='169.254.103.79', port=5500)
