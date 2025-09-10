import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()




cursor.execute("select * from preguntas order by  id desc")
a = cursor.fetchall()
print("Usuarios en la base de datos:")
for u in a:
    print(u)






print("Usuarios en la base de datos:")
for u in a:
    print(u)
    
# for u in respuestas:
#  print(u)

conn.close()