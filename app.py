from flask import Flask, render_template, request, jsonify, redirect, url_for, make_response
from datetime import datetime, timedelta
from mysql.connector import Error
from collections import defaultdict
from flask_cors import CORS
import hashlib
import jwt
import time
import mysql.connector
import os
import pandas as pd
import openpyxl
from dotenv import load_dotenv

load_dotenv() 

app = Flask(__name__)
# Configure CORS to allow credentials and specific origins
CORS(app, resources={r"/*": {"origins": ["http://127.0.0.1:5400"], "supports_credentials": True}})
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this to a secure secret key in production
app.config['MAX_LOGIN_ATTEMPTS'] = 5  # Maximum failed login attempts
app.config['LOGIN_TIMEOUT'] = 300  # Timeout in seconds (5 minutes)
app.config['SERVER_HOST'] = '127.0.0.1'  # Server IP address
app.config['SERVER_PORT'] = 5400  # Server port number

# Rate limiting storage
login_attempts = defaultdict(list)  # Store login attempts with timestamps
blocked_ips = defaultdict(float)  # Store blocked IPs with unblock time
table_sheet_map = {"Orders_library":"Orders","production":"Production","assembly":"Assembly"}
EXCEL_FILE = "./production.xlsx"
DB_HOST = os.getenv('DB_HOST')
DB_PORT = int(os.getenv('DB_PORT', '3306'))  # Default to port 3306 if not set
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
        )
        return conn
    except Error as e:
        print("Error connecting to MySQL:", e)
        return None

def update_excel():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if not os.path.exists(EXCEL_FILE):
        with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl") as writer:
            for table, sheet in table_sheet_map.items():
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                df = pd.DataFrame(rows)
                df.to_excel(writer, sheet_name=sheet, index=False)
        print("✅ Excel file created.")
    else:
        # No need to manually assign writer.book anymore!
        with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
            book = writer.book  # Optional: can access it, but don’t assign to it

            for table, sheet in table_sheet_map.items():
                if sheet in book.sheetnames:
                    existing_df = pd.read_excel(EXCEL_FILE, sheet_name=sheet)
                    last_id = existing_df["id"].max() if "id" in existing_df.columns else 0
                else:
                    existing_df = pd.DataFrame()
                    last_id = 0

                cursor.execute(f"SELECT * FROM {table} WHERE id > %s", (last_id,))
                new_rows = cursor.fetchall()
                new_df = pd.DataFrame(new_rows)

                if not new_df.empty:
                    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                    combined_df.to_excel(writer, sheet_name=sheet, index=False)
                    print(f"✅ Sheet '{sheet}' updated with {len(new_df)} new rows.")
                else:
                    print(f"ℹ No new data for sheet '{sheet}'.")

    cursor.close()
    conn.close()


# User authentication decorator
def requires_auth(f):
    def decorated(*args, **kwargs):
        # auth_header = request.headers.get('Authorization')
        token = request.headers.get('Cookie')[6:]
        
        if not token:
            return jsonify({'message': 'No authorization header'}), 401
        
        try:
            # token = auth_header.split(' ')[1]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({'message': 'Invalid token', 'error': str(e)}), 401
    decorated.__name__ = f.__name__
    return decorated

def check_auth():
    token = request.cookies.get('token')
    if not token:
        return False
    try:
        jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return True
    except:
        return False

@app.before_request
def require_login():
    public_routes = ['login', 'static']
    if not any(request.endpoint == route for route in public_routes):
        if not check_auth():
            return redirect(url_for('login'))

@app.route('/logout')
def logout():
    response = make_response(redirect(url_for('login')))
    response.delete_cookie('token')
    return response

@app.route('/')
def index():
    if not check_auth():
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/orders')
def orders():
    return render_template('orders.html')

@app.route('/specs')
def specs():
    return render_template('specs.html')
@app.route('/production')
def production():
    return render_template('production.html')

@app.route('/monitoring')
def monitoring():
    conn = get_db_connection()
    if not conn:
        return render_template('monitoring.html', orders=[])
    
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                ol.orderNum as order_id,
                ol.apnID as apn_id,
                ol.planned_quantity,
                COALESCE(s.name, ol.specification) as specification,
                ol.specs,
                ol.top,
                ol.bot,
                ol.front,
                ol.back,
                ol.left,
                ol.right
            FROM orders_library ol
            LEFT JOIN specifications s ON ol.specification = s.id
            WHERE s.name NOT IN ('Electrified Holder', 'Mechanical Holder', 'Wifi Holder')
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        orders = []
        for row in results:
            directions = {
                'Top': row['top'] if row['top'] is not None else "N/A",
                'Bottom': row['bot'] if row['bot'] is not None else "N/A",
                'Front': row['front'] if row['front'] is not None else "N/A",
                'Back': row['back'] if row['back'] is not None else "N/A",
                'Left': row['left'] if row['left'] is not None else "N/A",
                'Right': row['right'] if row['right'] is not None else "N/A"
            }   
            orders.append({
                'order_id': row['order_id'],
                'apn_id': row['apn_id'],
                'planned_quantity': row['planned_quantity'],
                'specification': row['specification'],
                'specs': row['specs'],
                'directions': directions,
            })
                    
        return render_template('monitoring.html', orders=orders)
    except Exception as e:
        print("Error:", e)
        return render_template('monitoring.html', orders=[])
    finally:
        conn.close()

@app.route('/add_order_to_library', methods=['POST'])
def add_order_to_library():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        data = request.get_json()
        order_number = data["orderNum"]
        apn_id = data["apnID"]
        Spec = data["specs"]
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
                orderNum, apnID,specs, specification, planned_quantity,
                top, bot, front, back, `left`, `right`, createdDate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        values = (
            order_number,
            apn_id,
            Spec,
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
        update_excel()
        conn.close()

@app.route('/all_orders', methods=['GET'])
def all_orders():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        # Read filter_specs query parameter, default False if not provided
        filter_specs = request.args.get('filter_specs', 'false').lower() == 'true'        # Base query with JOIN to specifications table


        query = """
            SELECT ol.orderNum, ol.apnID, ol.specs, ol.specification,
                   ol.planned_quantity, ol.createdDate, ol.top, ol.bot,
                   ol.front, ol.back, ol.left, ol.right,
                   s.name as specification_name
            FROM orders_library ol
            LEFT JOIN specifications s ON ol.specification = s.id
        """
        # Add filter if needed
        if filter_specs:
            query += " WHERE s.name NOT IN ('Electrified Holder', 'Mechanical Holder', 'Wifi Holder')"
        else :
            query += " WHERE s.name   IN ('Electrified Holder', 'Mechanical Holder', 'Wifi Holder')"
            
        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        orders = []
        for row in results:
            (orderNum, apnID, specs, specification, plannedQty, createdDate,
             top, bot, front, back, left, right, specification_name) = row
            orders.append({
                "orderNum": orderNum,
                "apnID": apnID,
                "specs": specs,
                "specification_id": specification,
                "specification_name": specification_name,
                "plannedQuantity": plannedQty,
                "createdDate": createdDate.strftime("%Y-%m-%d %H:%M:%S") if hasattr(createdDate, "strftime") else str(createdDate),
                "top": top,
                "bot": bot,
                "front": front,
                "back": back,
                "left": left,
                "right": right
            })

        return jsonify({"data": orders})

    except Exception as e:
        print("Error:", e)  # Log the error for debugging
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/production_history', methods=['GET'])
def production_history():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        query = """
            SELECT pr.order, pr.apn, pr.specification, pr.quantity,
                   pr.machine, pr.createdDate,
                   pr.top, pr.bot, pr.front, pr.back, pr.left, pr.right,
                   ol.specs, pr.user_firstname
            FROM production pr, orders_library ol
            WHERE pr.order = ol.orderNum AND pr.apn = ol.apnID
            ORDER BY pr.createdDate DESC
        """

        with conn.cursor() as cursor:
            cursor.execute(query)
            results = cursor.fetchall()

        data_list = []
        for row in results:
            (orderNum, apnID, specName, quantity, machine, createdDate,
             top, bot, front, back, left, right, specs, user_firstname) = row

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
                "right": right,
                "specs": specs,
                "user_firstname": user_firstname
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
        if not directions:
            return jsonify({"error": "At least one direction must be selected"}), 400
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
        with conn.cursor(dictionary=True) as cursor:
            # Check available quantities
            check_query = """
                SELECT top, bot, front, back, `left`, `right`
                FROM orders_library
                WHERE orderNum = %s AND apnID = %s
            """
            cursor.execute(check_query, (data["orderNumber"], data["apnID"]))
            available = cursor.fetchone()
            # Ensure all results are read before next execute
            while cursor.nextset():
                pass
            
            if not available:
                return jsonify({"error": "Order not found in database"}), 404

            # Verify quantities don't exceed available
            for direction, produced_qty in direction_values.items():
                if available[direction] is not None and produced_qty > available[direction]:
                    return jsonify({
                        "error": f"Quantity for '{direction}' ({produced_qty}) exceeds available quantity ({available[direction]})"
                    }, 400)            # Get username from token
            token = request.cookies.get('token')
            if not token:
                return jsonify({"error": "Authentication required"}), 401
            
            user_data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            username = user_data.get('username', 'Unknown')

            # Insert production record
            insert_query = """
                INSERT INTO production (
                    `order`, apn, specification, quantity, machine,
                    top, bot, front, back, `left`, `right`, createdDate,
                    user_firstname
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            insert_values = (
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
                timestamp,
                username
            )
            cursor.execute(insert_query, insert_values)

            conn.commit()
            
            # Dynamically build the update query and values to match only non-None directions
            update_fields = []
            update_values = []
            for direction in ["top", "bot", "front", "back", "left", "right"]:
                if available[direction] is not None:
                    field = f"`{direction}`" if direction in ["left", "right"] else direction
                    update_fields.append(f"{field} = {field} - %s")
                    update_values.append(direction_values[direction])
            update_query = f"""
                UPDATE orders_library SET
                {', '.join(update_fields)}
                WHERE orderNum = %s AND apnID = %s
            """
            update_values.extend([data["orderNumber"], data["apnID"]])
            cursor.execute(update_query, tuple(update_values))
            conn.commit()

            return jsonify({"message": "Production submitted successfully"})
    
    except Exception as e:
        print("Error:", e)  # Log the error for debugging
        return jsonify({"error": str(e)}), 500
    
    finally:
        update_excel()
        if conn:
            conn.close()       

from flask import request, jsonify
import traceback

@app.route('/update_directions', methods=['POST'])
def update_directions():
    conn = None
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        order_num = data.get('orderNum')
        apn_id = data.get('apnID')

        if not order_num or not apn_id:
            return jsonify({"error": "Order Number and APN-ID required"}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500

        # Check if order exists - use buffered cursor to consume all results and avoid 'Unread result found'
        check_query = "SELECT * FROM orders_library WHERE orderNum = %s AND apnID = %s"
        with conn.cursor(buffered=True) as cursor:  # <-- buffered=True added here
            cursor.execute(check_query, (order_num, apn_id))
            if not cursor.fetchone():
                return jsonify({"error": "Order not found"}), 404

        # Initialize directions dictionary
        directions = {
            "top": 0,
            "bot": 0,
            "left": 0,
            "right": 0,
            "front": 0,
            "back": 0
        }

        # Parse and validate direction values
        for direction in directions.keys():
            try:
                value = data.get(direction, 0)
                if not isinstance(value, (int, float)) and value is not None:
                    value = int(value)
                directions[direction] = None if value == 0 else value
            except (ValueError, TypeError):
                return jsonify({"error": f"Invalid value for direction '{direction}'"}), 400

        # Create directions string
        directions_list = [d for d in directions.keys() if directions[d] is not None]
        directions_string = "-".join(directions_list)

        # Update database
        update_query = """
            UPDATE orders_library SET
                top = %s, bot = %s, front = %s,
                back = %s, `left` = %s, `right` = %s,
                directions = %s
            WHERE orderNum = %s AND apnID = %s
        """
        with conn.cursor() as cursor:
            cursor.execute(update_query, (
                directions['top'], directions['bot'], directions['front'],
                directions['back'], directions['left'], directions['right'],
                directions_string, order_num, apn_id
            ))
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({"error": "Failed to update directions"}), 500
            conn.commit()

        return jsonify({"message": "Directions updated successfully"})

    except Exception as e:
        traceback.print_exc()  # Logs the full error to terminal
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return jsonify({"error": f"Server error: {str(e)}"}), 500

    finally:
        update_excel()
        if conn:
            try:
                conn.close()
            except:
                pass



@app.route('/get_remaining_quantities', methods=['GET'])
def get_remaining_quantities():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        order_num = request.args.get('orderNum')
        apn_id = request.args.get('apnID')

        if not order_num or not apn_id:
            return jsonify({"error": "Order number and APN ID are required"}), 400

        query = """
            SELECT 
                ol.orderNum,
                ol.apnID,
                ol.planned_quantity,
                ol.top - COALESCE(SUM(p.top), 0) as top,
                ol.bot - COALESCE(SUM(p.bot), 0) as bot,
                ol.front - COALESCE(SUM(p.front), 0) as front,
                ol.back - COALESCE(SUM(p.back), 0) as back,
                ol.`left` - COALESCE(SUM(p.`left`), 0) as `left`,
                ol.`right` - COALESCE(SUM(p.`right`), 0) as `right`,
                ol.specification
            FROM orders_library ol
            LEFT JOIN production p ON ol.orderNum = p.`order` AND ol.apnID = p.apn
            WHERE ol.orderNum = %s AND ol.apnID = %s
            GROUP BY ol.orderNum, ol.apnID, ol.planned_quantity, ol.top, ol.bot, 
                     ol.front, ol.back, ol.`left`, ol.`right`, ol.specification
        """

        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(query, (order_num, apn_id))
            result = cursor.fetchone()
            
            if not result:
                return jsonify({"error": "Order not found"}), 404
                
            return jsonify(result)

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/orders')
def get_orders():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    try:
        
        query = """
            SELECT ol.orderNum, ol.apnID, ol.specs, ol.specification,
                   ol.planned_quantity, ol.createdDate, ol.top, ol.bot,
                   ol.front, ol.back, ol.left, ol.right,
                   s.name as specification_name
            FROM orders_library ol
            LEFT JOIN specifications s ON ol.specification = s.id
            WHERE s.name NOT IN ('Electrified Holder', 'Mechanical Holder', 'Wifi Holder')
        """
        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        orders = []
        for row in results:
            (orderNum, apnID, specs, specification, plannedQty, createdDate,
             top, bot, front, back, left, right, specification_name) = row
            orders.append({
                "orderNum": orderNum,
                "apnID": apnID,
                "specs": specs,
                "specification_name": specification_name,
                "specification_id": specification,
                "plannedQuantity": plannedQty,
                "createdDate": createdDate.strftime("%Y-%m-%d %H:%M:%S") if hasattr(createdDate, "strftime") else str(createdDate),
                "top": top,
                "bot": bot,
                "front": front,
                "back": back,
                "left": left,
                "right": right
            })

        return jsonify({"data": orders})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/admin/users', methods=['GET'])
@requires_auth
def get_users():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT ID, FirstName, LastName, Badge, UserName FROM Users"
        cursor.execute(query)
        users = cursor.fetchall()        # Get permissions for each user
        for user in users:
            perm_query = """
                SELECT p.PageName, p.create, p.read, p.update, p.delete 
                FROM Permissions p 
                JOIN UserPermission up ON p.ID = up.permissionId
                WHERE up.userId = %s
            """
            cursor.execute(perm_query, (user['ID'],))
            user['permissions'] = cursor.fetchall()

        return jsonify({"users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/users', methods=['POST'])
@requires_auth
def create_user():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        data = request.get_json()
        
        # Hash the password
        password = hashlib.sha256(data['password'].encode()).hexdigest()
          # Insert user
        cursor = conn.cursor()
        user_query = """
            INSERT INTO Users (FirstName, LastName, Badge, UserName, `Password`)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(user_query, (
            data['firstName'],
            data['lastName'],
            data['badge'],
            data['userName'],
            password
        ))
        user_id = cursor.lastrowid

        # Insert permissions and user-permission relationships
        for perm in data['permissions']:
            # Insert permission
            # First check if permission exists
            check_perm_query = """
                SELECT ID FROM Permissions WHERE PageName = %s AND `create` = %s AND `read` = %s AND `update` = %s AND `delete` = %s
            """
            cursor.execute(check_perm_query, (
                perm['pageName'],
                perm['create'],
                perm['read'],
                perm['update'],
                perm['delete']
            ))
            existing_perm = cursor.fetchone()
            if existing_perm:
                perm_id = existing_perm[0]
            else:
                # Insert permission if not exists
                insert_perm_query = """
                    INSERT INTO Permissions (PageName, `create`, `read`, `update`, `delete`)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(insert_perm_query, (
                    perm['pageName'],
                    perm['create'],
                    perm['read'],
                    perm['update'],
                    perm['delete']
                ))
                perm_id = cursor.lastrowid

            
            # Create user-permission relationship
            up_query = """
                INSERT INTO UserPermission (userId, permissionId)
                VALUES (%s, %s)
            """
            cursor.execute(up_query, (user_id, perm_id))

        conn.commit()
        return jsonify({"message": "User created successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/users/<int:user_id>', methods=['GET'])
@requires_auth
def get_user(user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        
        # Get user details
        user_query = "SELECT ID, FirstName, LastName, Badge, UserName FROM Users WHERE ID = %s"
        cursor.execute(user_query, (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({"error": "User not found"}), 404        # Get user permissions
        perm_query = """
            SELECT p.PageName, p.`create`, p.`read`, p.`update`, p.`delete` 
            FROM Permissions p
            JOIN UserPermission up ON p.ID = up.permissionId
            WHERE up.userId = %s
        """
        cursor.execute(perm_query, (user_id,))
        user['permissions'] = cursor.fetchall()

        return jsonify(user)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/users/<int:user_id>', methods=['PUT'])
@requires_auth
def update_user(user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        data = request.get_json()
        cursor = conn.cursor()

        # Update user details
        update_fields = ["FirstName = %s", "LastName = %s", "Badge = %s", "UserName = %s"]
        params = [data['firstName'], data['lastName'], data['badge'], data['userName']]

        if data.get('password'):
            update_fields.append("Password = %s")
            password = hashlib.sha256(data['password'].encode()).hexdigest()
            params.append(password)

        params.append(user_id)
        
        user_query = f"""
            UPDATE Users 
            SET {', '.join(update_fields)}
            WHERE ID = %s
        """
        cursor.execute(user_query, params)        # Delete old user permissions relationships
        cursor.execute("DELETE FROM UserPermission WHERE userId = %s", (user_id,))
        
        # Insert new permissions and relationships
        for perm in data['permissions']:
            # Insert new permission
            perm_query = """
                INSERT INTO Permissions (PageName, `create`, `read`, `update`, `delete`)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(perm_query, (
                perm['pageName'],
                perm['create'],
                perm['read'],
                perm['update'],
                perm['delete']
            ))
            perm_id = cursor.lastrowid
            
            # Create new user-permission relationship
            up_query = """
                INSERT INTO UserPermission (userId, permissionId)
                VALUES (%s, %s)
            """
            cursor.execute(up_query, (user_id, perm_id))

        conn.commit()
        return jsonify({"message": "User updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/users/<int:user_id>', methods=['DELETE'])
@requires_auth
def delete_user(user_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        cursor = conn.cursor()
          # Delete user-permission relationships first
        cursor.execute("DELETE FROM UserPermission WHERE userId = %s", (user_id,))
        
        # Get permission IDs associated with this user
        cursor.execute("SELECT permissionId FROM UserPermission WHERE userId = %s", (user_id,))
        perm_ids = [row[0] for row in cursor.fetchall()]
        
        # Delete permissions
        if perm_ids:
            cursor.execute("DELETE FROM Permissions WHERE ID IN (%s)" % ','.join(['%s'] * len(perm_ids)), tuple(perm_ids))
        
        # Delete user
        cursor.execute("DELETE FROM Users WHERE ID = %s", (user_id,))
        conn.commit()
        return jsonify({"message": "User deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# Route for login page has been moved to the combined login route above

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        # Check if user is already logged in
        if request.cookies.get('token'):
            return redirect(url_for('index'))
        return render_template('login.html')

    # Handle POST request
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        remember_me = data.get('remember_me', False)
        
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        # Rate limiting: check if IP is blocked
        ip_address = request.remote_addr
        can_attempt, error_message = check_rate_limit(ip_address)
        if not can_attempt:
            return jsonify({"error": error_message}), 429

        cursor = conn.cursor(dictionary=True)
          # Hash the password and check credentials
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        query = "SELECT ID, UserName, FirstName, LastName, Badge FROM Users WHERE UserName = %s AND Password = %s"
        cursor.execute(query, (username, hashed_password))
        user = cursor.fetchone()
        
        if user:
            # Successful login, reset login attempts
            login_attempts[ip_address] = []
            
            # Calculate token expiration
            expiration = datetime.utcnow() + timedelta(days=30 if remember_me else 1)
            
            # Generate JWT token
            token = jwt.encode({
                'user_id': user['ID'],
                'username': user['UserName'],
                'firstname': user['FirstName'],
                'lastname': user['LastName'],
                'badge': user['Badge'],
                'exp': expiration
            }, app.config['SECRET_KEY'], algorithm='HS256')
            
            response = make_response(jsonify({
                "message": "Login successful",
                "token": token,
                "redirect": url_for('index')
            }))
            
            # Set secure cookie with token
            response.set_cookie(
                'token', 
                token,
                httponly=True,
                secure=False,  # Set to True in production with HTTPS
                samesite='Lax',
                max_age=2592000 if remember_me else 86400  # 30 days if remember me, else 24 hours
            )
            return response
        else:
            # Failed login, record attempt
            attempts_left = handle_failed_login(ip_address)
            if attempts_left > 0:
                return jsonify({"error": f"Invalid credentials. {attempts_left} attempts remaining"}), 401
            else:
                return jsonify({"error": "Too many login attempts. Please try again later."}), 429
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

def check_rate_limit(ip):
    current_time = time.time()
    
    # Check if IP is blocked
    if ip in blocked_ips:
        if current_time < blocked_ips[ip]:
            block_remaining = int(blocked_ips[ip] - current_time)
            return False, f"Too many login attempts. Please try again in {block_remaining} seconds."
        else:
            # Unblock IP if timeout has passed
            del blocked_ips[ip]
            login_attempts[ip].clear()
    
    # Clean old attempts
    login_attempts[ip] = [t for t in login_attempts[ip] if current_time - t < app.config['LOGIN_TIMEOUT']]
    
    # Check number of recent attempts
    if len(login_attempts[ip]) >= app.config['MAX_LOGIN_ATTEMPTS']:
        blocked_ips[ip] = current_time + app.config['LOGIN_TIMEOUT']
        return False, "Too many login attempts. Please try again later."
    
    return True, None

def handle_failed_login(ip):
    current_time = time.time()
    login_attempts[ip].append(current_time)
    attempts_left = app.config['MAX_LOGIN_ATTEMPTS'] - len(login_attempts[ip])
    return attempts_left

@app.route('/assembly_monitoring')
def assembly_monitoring():
    return render_template('assembly_monitoring.html')

@app.route('/assembly_monitoring_data')
def assembly_monitoring_data():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT 
                ol.orderNum AS `order`,
                ol.apnID AS apn_id,
                MAX(a.specification) AS specification,
                ol.specs,
                ol.planned_quantity,
                COALESCE(SUM(a.quantity_assembled), 0) AS quantity_assembled,
                ol.planned_quantity - COALESCE(SUM(a.quantity_assembled), 0) AS remaining_quantity
            FROM orders_library ol
            LEFT JOIN assembly a ON ol.orderNum = a.`order` AND ol.apnID = a.apn
            LEFT JOIN specifications s ON ol.specification = s.id
            WHERE s.name  IN ('Electrified Holder', 'Mechanical Holder', 'Wifi Holder')
            GROUP BY 
                ol.orderNum, 
                ol.apnID, 
                ol.specs, 
                ol.planned_quantity
            ORDER BY ol.orderNum DESC
        """
        
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(query)
            orders = cursor.fetchall()
            print("Fetched orders:", orders)
            return jsonify({"orders": orders})

    except Exception as e:
        print("Error in /assembly_monitoring_data:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
        
        
from flask import jsonify
from datetime import datetime

@app.route('/assembly_chart_data')
def assembly_chart_data():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        
        query = """
SELECT 
                DATE(a.created_date) as date,
                a.apn,
                ol.planned_quantity,
                SUM(a.quantity_assembled) as daily_quantity,
                s.`name` as specification
            FROM assembly a, orders_library ol
            JOIN specifications s ON s.id = ol.specification
              where a.`order` = ol.orderNum AND a.apn = ol.apnID
            GROUP BY DATE(a.created_date), a.apn, ol.planned_quantity, ol.specification
            ORDER BY date ASC
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        chart_data = {
            'labels': [],
            'datasets': [],
            'orders': {}
        }

        for row in results:
            date_value = row['date']
            date_str = date_value.strftime('%Y-%m-%d') if hasattr(date_value, 'strftime') else str(date_value)
            
            if date_str not in chart_data['labels']:
                chart_data['labels'].append(date_str)
            
            order_id = row['apn']
            if order_id not in chart_data['orders']:
                chart_data['orders'][order_id] = {
                    'label': f"APN {order_id} ({row['specification']})",
                    'data': [],
                    'planned_quantity': row['planned_quantity']
                }
            
            chart_data['orders'][order_id]['data'].append({
                'x': date_str,
                'y': row['daily_quantity']
            })
        
        for order_id, order_data in chart_data['orders'].items():
            chart_data['datasets'].append({
                'label': order_data['label'],
                'data': order_data['data'],
                'tension': 0.4,
                'planned_quantity': order_data['planned_quantity']
            })
        
        return jsonify(chart_data)

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()




@app.route('/assembly_history', methods=['GET'])
def assembly_history():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        query = """
            SELECT 
                distinct (`order`),
                a.apn, 
                a.specification,
                ol.specs,
                a.quantity_assembled as quantityAssembled,
                a.created_date as dateTime,
                UserName
            FROM assembly a
            INNER JOIN orders_library ol ON a.`order` = ol.orderNum AND a.apn = ol.apnID
            LEFT JOIN users u ON a.user_id = u.ID
            ORDER BY a.created_date DESC
        """

        with conn.cursor() as cursor:
            cursor.execute(query)
            results = cursor.fetchall()

        data_list = []
        for row in results:
            (orderNumber, apnID, specification, specs, quantityAssembled, dateTime, username) = row
            data_list.append({
                "orderNumber": orderNumber,
                "apnID": apnID,
                "specification": specification,
                "specs": specs,
                "quantityAssembled": quantityAssembled,
                "dateTime": dateTime.strftime("%Y-%m-%d %H:%M:%S") if hasattr(dateTime, "strftime") else str(dateTime),
                "user_name": username
            })

        return jsonify({"data": data_list})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/submit_assembly', methods=['POST'])
def submit_assembly():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Get user info from token
        token = request.cookies.get('token')
        if not token:
            return jsonify({"error": "Authentication required"}), 401

        user_data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        userid = user_data.get('user_id', 'Unknown')

        # Extract fields from frontend JSON (which uses camelCase keys)
        order_number = data.get('orderNumber')  # frontend sends "orderNumber"
        apn_id = data.get('apnID')
        specification = data.get('specification')
        quantity = data.get('quantity')

        # Validate quantity
        try:
            quantity = int(quantity)
            if quantity <= 0:
                return jsonify({"error": "Quantity must be greater than 0"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid quantity value"}), 400

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Check for missing fields
        if not all([order_number, apn_id, specification, quantity]):
            return jsonify({"error": "Missing required fields"}), 400

        # ✅ Use correct SQL column names — especially `order` (not `orderNumber`)
        query = """
            INSERT INTO assembly 
            (`order`, apn, specification, quantity_assembled, user_id, created_date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (
                order_number,        # maps to SQL `order` column
                apn_id,              # maps to SQL `apn`
                specification,       # maps to SQL `specification`
                quantity,            # maps to SQL `quantity_assembled`
               userid,            # maps to SQL `user_firstname`
                timestamp            # maps to SQL `created_date`
            ))
            conn.commit()

        return jsonify({"message": "Assembly submitted successfully"})

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        update_excel()
        conn.close()
        
        
@app.route('/all_specifications', methods=['GET'])
def all_specifications():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500

    try:

        query = """
            SELECT  id, name
            FROM specifications 
        """

        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        specifications = []
        for row in results:
    
            (id, name) = row
            specifications.append({
                "id": id,
                "name": name
            })

        return jsonify({"data": specifications})
    except Exception as e:
        print("Error:", e)  # Log the error for debugging
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()



@app.route('/assembly')
def assembly():
    return render_template('assembly.html')


from flask import send_file

@app.route('/export_excel')
def export_excel():
    update_excel()
    return send_file(EXCEL_FILE, as_attachment=True)
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5600, debug=True)

