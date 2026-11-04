def find(cursor, name):
    cursor.execute("SELECT id FROM users WHERE name = %s", (name,))
