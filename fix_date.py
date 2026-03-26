#!/usr/bin/env python3
"""
Fix script: Update April lunch date from 18th to 11th April 2026
Run this on PythonAnywhere after pulling the latest code.
"""

import sqlite3
import os

def fix_april_date():
    """Update the April lunch date in the database"""
    db_path = 'instance/lunch_bookings.db'
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        print("Make sure you're running this from the project root directory.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check current date
    cursor.execute("SELECT id, lunch_date FROM lunch_date WHERE id = 1;")
    result = cursor.fetchone()
    
    if result:
        current_id, current_date = result
        print(f"Current April lunch date in database: {current_date}")
        
        if current_date == '2026-04-18':
            # Update the date
            cursor.execute("UPDATE lunch_date SET lunch_date = '2026-04-11' WHERE id = 1;")
            conn.commit()
            print("✅ Updated to: 2026-04-11")
        elif current_date == '2026-04-11':
            print("✅ Date is already correct (2026-04-11)")
        else:
            print(f"⚠️ Unexpected date found: {current_date}")
    else:
        print("⚠️ No lunch date found with ID 1")
    
    # Show all lunch dates
    print("\nAll lunch dates:")
    cursor.execute("SELECT id, lunch_date, is_bookable FROM lunch_date ORDER BY lunch_date;")
    for row in cursor.fetchall():
        print(f"  ID {row[0]}: {row[1]} (Bookable: {'Yes' if row[2] else 'No'})")
    
    # Check for any bookings
    cursor.execute("SELECT COUNT(*) FROM booking WHERE cancelled_at IS NULL;")
    booking_count = cursor.fetchone()[0]
    print(f"\nTotal active bookings: {booking_count}")
    
    conn.close()
    print("\nDone!")

if __name__ == '__main__':
    fix_april_date()
