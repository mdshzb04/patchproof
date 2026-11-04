def find(cursor, name):
    cursor.execute(f"SELECT id FROM users WHERE name = '{name}'")
