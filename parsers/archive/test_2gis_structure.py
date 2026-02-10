"""
Тестовый скрипт для изучения структуры 2GIS
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import json

# Инициализация браузера
options = Options()
options.add_argument('--window-size=1920,1080')
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

url = "https://2gis.kz/almaty/firm/70000001057770550/tab/reviews"
driver.get(url)

print("Страница загружена. Ждем 5 секунд...")
time.sleep(5)

# Проверяем initialState до клика
initial_before = driver.execute_script('return window.initialState')
reviews_before = initial_before.get('data', {}).get('review', {})
print(f"\n[ДО КЛИКА] Отзывов в initialState: {len(reviews_before)}")

# Кликаем на "Показать еще" 5 раз
for i in range(5):
    button = driver.execute_script("""
        const buttons = document.querySelectorAll('button, div[role="button"], a');
        for (let btn of buttons) {
            if (btn.textContent.includes('Показать') ||
                btn.textContent.includes('ещё') ||
                btn.textContent.includes('еще')) {
                return btn;
            }
        }
        return null;
    """)

    if button:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", button)
        print(f"\nКлик #{i+1} выполнен. Ждем 2 секунды...")
        time.sleep(2)

        # Проверяем initialState после клика
        initial_after = driver.execute_script('return window.initialState')
        reviews_after = initial_after.get('data', {}).get('review', {})
        print(f"  Отзывов в initialState: {len(reviews_after)}")
    else:
        print("\nКнопка не найдена!")
        break

# Проверяем все доступные ключи в window
print("\n\n=== Доступные глобальные объекты ===")
keys = driver.execute_script("""
    const keys = [];
    for (let key in window) {
        if (key.includes('state') || key.includes('State') || key.includes('review') || key.includes('data')) {
            keys.push(key);
        }
    }
    return keys;
""")
print(keys[:20])  # Первые 20

# Проверяем количество DOM элементов с отзывами
print("\n\n=== DOM элементы ===")
review_count = driver.execute_script("""
    // Пробуем разные селекторы
    const selectors = [
        '[data-review-id]',
        '[class*="review"]',
        '[class*="Review"]',
        'article',
        '[role="article"]'
    ];

    for (let sel of selectors) {
        const elements = document.querySelectorAll(sel);
        if (elements.length > 10) {
            return {selector: sel, count: elements.length};
        }
    }
    return null;
""")
print(f"Найдено элементов: {review_count}")

input("\nНажмите Enter чтобы закрыть браузер...")
driver.quit()
