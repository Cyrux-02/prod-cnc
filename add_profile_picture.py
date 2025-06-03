import mysql.connector
from mysql.connector import Error

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="127.0.0.1",
            port=3306,
            user="root",
            password="abdellahA2002",
            database="cnc_data"
        )
        return conn
    except Error as e:
        print("Error connecting to MySQL:", e)
        return None

def add_profile_picture_column():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            print("Failed to connect to database")
            return False

        cursor = conn.cursor()
        
        # Check if column exists first
        check_query = """
            SELECT COUNT(*) 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = 'cnc_data'
            AND TABLE_NAME = 'Users'
            AND COLUMN_NAME = 'ProfilePicture'
        """
        cursor.execute(check_query)
        
        if cursor.fetchone()[0] == 0:
            # Add the column if it doesn't exist
            alter_query = """
                ALTER TABLE Users 
                ADD COLUMN ProfilePicture VARCHAR(255) DEFAULT NULL
                AFTER Password
            """
            cursor.execute(alter_query)
            conn.commit()
            print("Successfully added ProfilePicture column to Users table")
            return True
        else:
            print("ProfilePicture column already exists")
            return True
    
    except mysql.connector.Error as e:
        print(f"MySQL Error: {str(e)}")
        return False
    except Exception as e:
        print(f"Error: {str(e)}")
        return False
    finally:
        if cursor:
            try:
                cursor.close()
            except Error as e:
                print(f"Error closing cursor: {str(e)}")
        if conn:
            try:
                conn.close()
            except Error as e:
                print(f"Error closing connection: {str(e)}")

if __name__ == "__main__":
    add_profile_picture_column()
