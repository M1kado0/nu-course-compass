from .connection import get_db_connection

def main():
    with get_db_connection() as conn:
        result = conn.execute("SELECT 1").fetchone()
        print(result)

if __name__ == "__main__":
    main()