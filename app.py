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

@app.route('/submit', methods=['POST'])
def submit():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        data = request.get_json()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        query = """
            INSERT INTO cnc_orders (quantity, apn, createdDate, orderNum, specId)
            VALUES (%s, %s, %s, %s, %s)
        """
        values = (
            data["quantityProduced"],
            data["apnID"],
            timestamp,
            data["orderNumber"],
            data["specification"]
        )

        with conn.cursor() as cursor:
            cursor.execute(query, values)
            conn.commit()

        return jsonify({"message": "Data received", "timestamp": timestamp})
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
                SELECT quantity, apn, createdDate, orderNum, name
                FROM cnc_orders
                JOIN specifications ON cnc_orders.specId = specifications.id
                WHERE DATE(createdDate) >= %s and DATE(createdDate) <= %s
            """
            params = (dateFrom,dateTo)
        elif dateFrom:
            query = """
                SELECT quantity, apn, createdDate, orderNum, name
                FROM cnc_orders
                JOIN specifications ON cnc_orders.specId = specifications.id
                WHERE DATE(createdDate) >= %s
            """
            params = (dateFrom,)
        elif dateTo:
            query = """
                SELECT quantity, apn, createdDate, orderNum, name
                FROM cnc_orders
                JOIN specifications ON cnc_orders.specId = specifications.id
                WHERE DATE(createdDate) <= %s
            """
            params = (dateTo,)
        else:
            query = """
                SELECT quantity, apn, createdDate, orderNum, name
                FROM cnc_orders
                JOIN specifications ON cnc_orders.specId = specifications.id
            """
            params = ()

        with conn.cursor() as cursor:
            cursor.execute(query, params)
            results = cursor.fetchall()

        data_list = []
        for row in results:
            quantity, apn, createdDate, orderNum, specName = row
            data_list.append({
                "quantityProduced": quantity,
                "apnID": apn,
                "dateTime": createdDate.strftime("%Y-%m-%d %H:%M:%S") if hasattr(createdDate, "strftime") else str(createdDate),
                "orderNumber": orderNum,
                "specification": specName,
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
        query = """
            INSERT INTO orders_library (orderNum, apnID, specification, planned_quantity)
            VALUES (%s, %s, %s, %s)
        """
        values = (
            data["orderNumber"],
            data["apnID"],
            data["specification"],
            data["plannedQuantity"]
        )

        with conn.cursor() as cursor:
            cursor.execute(query, values)
            conn.commit()

        return jsonify({"message": "Order added to library successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(host='169.254.103.79', port=5000)
