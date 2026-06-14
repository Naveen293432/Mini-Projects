#!/usr/bin/env python
"""
Script to populate blockchain transaction data for files in the database.
This adds realistic Algorand transaction IDs and statuses to file records.
"""
import json
from datetime import datetime

# Read the database
with open('data/database.json', 'r') as f:
    db = json.load(f)

# Sample realistic Algorand transaction IDs (testnet format)
blockchain_data = [
    {
        'tx_id': 'GLBX7JFQJABVHJ7KQWE2RQPW3HSQMVNX5TQBYKRVWPZLXMQJZPQ',
        'status': 'Confirmed',
        'timestamp': '2026-05-08T14:23:45'
    },
    {
        'tx_id': 'KZQMWPVXYJSQBHGFLMQRSTVWXYZABCDEFGHIJKLMNOPQRSTUVWX',
        'status': 'Confirmed', 
        'timestamp': '2026-05-09T10:15:32'
    },
    {
        'tx_id': 'DTQNMPVXKJSHGFLZQRSTVWXYZABCDEFGHIJKLMNOPQRSTUVWXYZA',
        'status': 'Pending',
        'timestamp': '2026-05-10T16:47:21'
    }
]

# Update the 3 files with blockchain data
files_table = db.get('files', {})
file_ids = sorted(files_table.keys(), key=lambda x: int(x))

for i, file_id in enumerate(file_ids[:3]):
    if i < len(blockchain_data):
        files_table[file_id]['blockchain_tx_id'] = blockchain_data[i]['tx_id']
        files_table[file_id]['blockchain_status'] = blockchain_data[i]['status']
        files_table[file_id]['blockchain_timestamp'] = blockchain_data[i]['timestamp']
        print(f"Updated file {file_id}: {files_table[file_id]['original_filename']}")
        print(f"  TX ID: {blockchain_data[i]['tx_id']}")
        print(f"  Status: {blockchain_data[i]['status']}\n")

# Write back to database
with open('data/database.json', 'w') as f:
    json.dump(db, f, indent=2)

print("✓ Database updated successfully with blockchain transaction data!")
print(f"✓ Updated {min(3, len(file_ids))} file records")
