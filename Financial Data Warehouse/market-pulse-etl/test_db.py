import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def test_connection():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not found in .env file.")
        return

    # Check if host is db.yybztoiynqyuxpkcpuqw.supabase.co
    # If so, try to find an A record or fallback
    print(f"Connecting to: {DATABASE_URL.split('@')[-1].split(':')[0]}...") 
    
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            if result.fetchone()[0] == 1:
                print("SUCCESS: Database connection established.")
    except Exception as e:
        print("FAIL: Connection Failed!")
        print(f"Error details: {str(e)}")

if __name__ == "__main__":
    test_connection()
