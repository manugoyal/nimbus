import torndb
import logging
import argparse

parser = argparse.ArgumentParser(description='A cloud storage unification service')

db = torndb.Connection('127.0.0.1', '', 'root')
db.execute('CREATE DATABASE IF NOT EXISTS nimbus')
db.execute('use nimbus')
db.execute('CREATE TABLE IF NOT EXISTS test(a int, b int)')
db.execute('INSERT INTO test VALUES (1, 2), (3, 4)')
print db.query('SELECT * FROM test')

if __name__ == '__main__':
    
