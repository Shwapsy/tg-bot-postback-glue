#!/usr/bin/env python3
"""
Скрипт для тестирования постбэков
Использование: python test_postback.py
"""

import requests
import json

# Настройки
BASE_URL = "http://localhost:5000"  # Для локального теста
# BASE_URL = "https://ваш-домен.onrender.com"  # Для продакшена

def test_registration():
    print("\n🧪 Тест: Регистрация")
    data = {
        "reg": "true",
        "conf": "false",
        "ftd": "false",
        "dep": "false",
        "trader_id": "TEST123456",
        "click_id": "test_click_123",
        "site_id": "test_site",
        "a": "T2ye3EBrPxd4Se",
        "ac": "postbacks-test"
    }
    response = requests.post(f"{BASE_URL}/postback", json=data)
    print(f"Статус: {response.status_code}")
    print(f"Ответ: {response.json()}")
    return response.status_code == 200

def test_first_deposit():
    print("\n🧪 Тест: Первый депозит")
    data = {
        "reg": "false",
        "conf": "true",
        "ftd": "true",
        "dep": "false",
        "trader_id": "TEST123456",
        "sumdep": "100",
        "click_id": "test_click_123",
        "site_id": "test_site",
        "a": "T2ye3EBrPxd4Se",
        "ac": "postbacks-test"
    }
    response = requests.post(f"{BASE_URL}/postback", json=data)
    print(f"Статус: {response.status_code}")
    print(f"Ответ: {response.json()}")
    return response.status_code == 200

def test_get_method():
    print("\n🧪 Тест: GET метод")
    params = {
        "reg": "true",
        "ftd": "true",
        "trader_id": "TEST123456",
        "sumdep": "100"
    }
    response = requests.get(f"{BASE_URL}/postback", params=params)
    print(f"Статус: {response.status_code}")
    print(f"Ответ: {response.json()}")
    return response.status_code == 200

def check_mongodb():
    print("\n🧪 Проверка MongoDB")
    try:
        from pymongo import MongoClient
        MONGODB_URI = "mongodb+srv://lolpoc48_db_user:knpw7BahfpIUOUpQ@cluster0.aj25qoh.mongodb.net/?appName=Cluster0"
        client = MongoClient(MONGODB_URI)
        client.admin.command('ping')
        db = client['pocketoption_bot']
        users_count = db['users'].count_documents({})
        postbacks_count = db['postbacks'].count_documents({})
        print(f"✅ MongoDB подключен")
        print(f"👥 Пользователей: {users_count}")
        print(f"📮 Постбэков: {postbacks_count}")
        client.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def main():
    print("=" * 50)
    print("🚀 PocketOption Bot - Тестирование")
    print("=" * 50)
    
    check_mongodb()
    
    try:
        test_registration()
        test_first_deposit()
        test_get_method()
        print("\n✅ Все тесты завершены!")
    except requests.exceptions.ConnectionError:
        print("\n❌ Сервер не запущен. Запустите: python bot.py")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")

if __name__ == "__main__":
    main()