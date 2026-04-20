# -*- coding: utf-8 -*-
import psycopg
import os

db_url = "postgresql://postgres:123456@127.0.0.1:5432/china_web_db"

translations = {
    'Home': 'Trang Chủ',
    'About Us': 'Giới Thiệu',
    'Qualification Honor': 'Năng Lực & Danh Hiệu',
    'Business Display': 'Lĩnh Vực Hoạt Động',
    'Project Case': 'Dự Án',
    'News Center': 'Tin Tức',
    'Contact Us': 'Liên Hệ',
    'Subsidiary': 'Công Ty Con',
    'Branch': 'Chi Nhánh',
    'Join Us': 'Tuyển Dụng',
    'Video': 'Video Sản Phẩm'
}

def translate():
    try:
        conn = psycopg.connect(db_url)
        cursor = conn.cursor()
        
        # Translate main titles
        for eng, vie in translations.items():
            cursor.execute("UPDATE menu_items SET title = %s WHERE title = %s", (vie, eng))
            
        # Ensure 'Sản phẩm' exists
        cursor.execute("SELECT id FROM menu_items WHERE title = 'Sản phẩm'")
        if not cursor.fetchone():
             cursor.execute("INSERT INTO menu_items (menu_id, title, url, sort_order) VALUES (1, 'Sản phẩm', '/products', 35)")
        
        conn.commit()
        cursor.close()
        conn.close()
    except:
        pass

if __name__ == "__main__":
    translate()
