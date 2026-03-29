import duckdb

con = duckdb.connect('/Users/songruikang/Research/data-agent/sample.duckdb')

con.execute('CREATE TABLE customers (customer_id INTEGER, name VARCHAR, city VARCHAR, signup_date DATE)')
con.execute("INSERT INTO customers VALUES (1,'Alice','Beijing','2023-01-10'),(2,'Bob','Shanghai','2023-03-15'),(3,'Charlie','Guangzhou','2023-05-20'),(4,'Diana','Shenzhen','2023-07-08')")

con.execute('CREATE TABLE products (product_id INTEGER, name VARCHAR, category VARCHAR, price DECIMAL(10,2))')
con.execute("INSERT INTO products VALUES (1,'MacBook Pro','Electronics',12999),(2,'iPhone 15','Electronics',7999),(3,'AirPods Pro','Electronics',1799),(4,'Desk Chair','Furniture',2499),(5,'Standing Desk','Furniture',4999)")

con.execute('CREATE TABLE orders (order_id INTEGER, customer_id INTEGER, product_id INTEGER, quantity INTEGER, order_date DATE)')
con.execute("INSERT INTO orders VALUES (1,1,1,1,'2024-01-15'),(2,2,2,1,'2024-01-20'),(3,1,3,2,'2024-02-03'),(4,3,4,1,'2024-02-10'),(5,2,5,1,'2024-02-15'),(6,4,2,1,'2024-03-01'),(7,1,4,1,'2024-03-05'),(8,3,3,1,'2024-03-10')")

print("Tables created:")
print(con.execute("SHOW TABLES").fetchdf())
print("\n--- customers ---")
print(con.execute("SELECT * FROM customers").fetchdf())
print("\n--- products ---")
print(con.execute("SELECT * FROM products").fetchdf())
print("\n--- orders ---")
print(con.execute("SELECT * FROM orders").fetchdf())

con.close()
print("\nDone!")
