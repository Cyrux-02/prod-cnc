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

@app.route('/submit', methods=['POST'])
def submit():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        data = request.get_json()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        required = ["orderNumber", "apn", "specification", "quantity"]
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
            INSERT INTO cnc_orders (
                orderNum, apn, specId, quantity,
                top, bot, front, back, `left`, `right`, createdDate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            data["orderNumber"],
            data["apn"],
            data["specification"],
            quantity,
            direction_values["top"],
            direction_values["bot"],
            direction_values["front"],
            direction_values["back"],
            direction_values["left"],
            direction_values["right"],
            timestamp
        )
        print(data)
        with conn.cursor() as cursor:
            cursor.execute(query, values)
            conn.commit()

        return jsonify({"message": "CNC order submitted successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/history', methods=['GET'])
def history():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        dateFrom = request.args.get('dateFrom')
        dateTo = request.args.get('dateTo')

        if dateFrom and dateTo:
            query = """
                SELECT quantity, apn, createdDate, orderNum, name,
                       top, bot, front, back, `left`, `right`
                FROM cnc_orders
                JOIN specifications ON cnc_orders.specId = specifications.id
                WHERE DATE(createdDate) >= %s and DATE(createdDate) <= %s
            """
            params = (dateFrom, dateTo)
        elif dateFrom:
            query = """
                SELECT quantity, apn, createdDate, orderNum, name,
                       top, bot, front, back, `left`, `right`
                FROM cnc_orders
                JOIN specifications ON cnc_orders.specId = specifications.id
                WHERE DATE(createdDate) >= %s
            """
            params = (dateFrom,)
        elif dateTo:
            query = """
                SELECT quantity, apn, createdDate, orderNum, name,
                       top, bot, front, back, `left`, `right`
                FROM cnc_orders
                JOIN specifications ON cnc_orders.specId = specifications.id
                WHERE DATE(createdDate) <= %s
            """
            params = (dateTo,)
        else:
            query = """
                SELECT quantity, apn, createdDate, orderNum, name,
                       top, bot, front, back, `left`, `right`
                FROM cnc_orders
                JOIN specifications ON cnc_orders.specId = specifications.id
            """
            params = ()

        with conn.cursor() as cursor:
            cursor.execute(query, params)
            results = cursor.fetchall()

        data_list = []
        for row in results:
            (quantity, apn, createdDate, orderNum, specName,
             top, bot, front, back, left, right) = row

            data_list.append({
                "quantityProduced": quantity,
                "apnID": apn,
                "dateTime": createdDate.strftime("%Y-%m-%d %H:%M:%S") if hasattr(createdDate, "strftime") else str(createdDate),
                "orderNumber": orderNum,
                "specification": specName,
                "top": top,
                "bot": bot,
                "front": front,
                "back": back,
                "left": left,
                "right": right
            })

        return jsonify({"message": "Data received", "data": data_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


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
            SELECT orderNum, apnID, specification, planned_quantity,
                   createdDate
            FROM orders_library
        """

        with conn.cursor() as cursor:
            cursor.execute(query)
            results = cursor.fetchall()

        data_list = []
        for row in results:
            data_list.append({
                "orderNumber": row[0],
                "apnID": row[1],
                "specification": row[2],
                "plannedQuantity": row[3],
                "createdDate": row[4].strftime("%Y-%m-%d %H:%M:%S") if hasattr(row[4], "strftime") else str(row[4])
            })

        return jsonify({"data": data_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/production')
def production():
    return render_template('production.html')

@app.route('/submit_production', methods=['POST'])
def submit_production():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        data = request.get_json()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        order_number = data["orderNumber"]
        apn_id = data["apnID"]
        specification = data["specification"]
        quantity = int(data["quantity"])
        machine = data["machine"]
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
            INSERT INTO production_records (
                orderNum, apnID, specId, quantity, machine,
                top, bot, front, back, `left`, `right`, createdDate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            order_number,
            apn_id,
            specification,
            quantity,
            machine,
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

        return jsonify({"message": "Production record submitted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/production_history', methods=['GET'])
def production_history():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        query = """
            SELECT pr.orderNum, pr.apnID, s.name, pr.quantity,
                   pr.machine, pr.createdDate,
                   pr.top, pr.bot, pr.front, pr.back, pr.left, pr.right
            FROM production_records pr
            JOIN specifications s ON pr.specId = s.id
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

if __name__ == '__main__':
    app.run(host='169.254.103.79', port=5500)
