import psycopg

try:
    print("Trying psycopg direct connection...")
    conn = psycopg.connect("postgresql://neondb_owner:*****@ep-wild-base-axfhbm3c.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require", connect_timeout=5)
    print("Success:", conn)
    conn.close()
except Exception as e:
    print("Failed:", type(e).__name__, e)
