import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
url = os.getenv("NEON_DB_URL")
print("NEON_DB_URL =", url)

engine = create_engine(url)

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))
    print("DB OK, SELECT 1 ->", list(result))
