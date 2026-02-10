"""
ФИНАЛЬНЫЙ РАБОЧИЙ ПАРСЕР 2GIS
Комбинированный подход для надежного извлечения отзывов с рейтингами и датами
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import random
import json
import re
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)
@dataclass
class Review:
    author: str
    author_reviews_count: int # Количество отзывов автора
    rating: float
    text: str
    date: str
@dataclass
class Place:
    name: str
    address: str
    category: str
    rating: float
    reviews_count: int
    phone: str
    url: str
    reviews: List[Review]
class SimpleTwoGISScraper:
    """Простой и надежный парсер 2GIS"""
   
    def __init__(self, headless: bool = False):
        self.driver = self._init_driver(headless)
        self.wait = WebDriverWait(self.driver, 15)
   
    def _init_driver(self, headless: bool):
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
       
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        logger.info("✅ Chrome запущен")
        return driver
   
    def search_places(self, query: str, city: str = "almaty", max_results: int = 50) -> List[str]:
        """Поиск заведений"""
        search_url = f"https://2gis.kz/{city}/search/{query}"
        logger.info(f"🔍 Поиск: {query}")
       
        self.driver.get(search_url)
        time.sleep(5)
       
        # Прокрутка
        for i in range(3):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
       
        # Собираем URLs
        links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/firm/')]")
        urls = []
       
        for link in links:
            try:
                href = link.get_attribute('href')
                if href and '/firm/' in href:
                    url = href.split('?')[0].split('#')[0]
                    if url not in urls and url.startswith('http'):
                        urls.append(url)
            except:
                continue
       
        logger.info(f"📍 Найдено {len(urls)} заведений")
        return urls[:max_results]
   
    def get_place_data(self, url: str) -> Place:
        """Получение данных о заведении"""
        logger.info(f"📄 Парсим: {url}")
       
        self.driver.get(url)
        time.sleep(5) # Ждем загрузки
       
        # Получаем HTML
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
       
        # Название из title
        title_tag = soup.find('title')
        title_text = title_tag.text if title_tag else ""
       
        # Парсим title: "Название, категория, адрес — 2ГИС"
        parts = [p.strip() for p in title_text.split(',')]
       
        name = parts[0] if len(parts) > 0 else "Неизвестно"
        category = parts[1] if len(parts) > 1 else "Не указано"
        address = parts[2].split('—')[0].strip() if len(parts) > 2 else "Не указан"
       
        # Рейтинг и отзывы - ищем в тексте страницы
        page_text = self.driver.page_source
       
        rating = 0.0
        rating_match = re.search(r'"rating":\s*(\d+\.?\d*)', page_text)
        if rating_match:
            try:
                rating = float(rating_match.group(1))
            except:
                pass
       
        reviews_count = 0
        reviews_match = re.search(r'"reviewsCount":\s*(\d+)', page_text)
        if reviews_match:
            try:
                reviews_count = int(reviews_match.group(1))
            except:
                pass
       
        # Если не нашли в JSON, ищем в тексте
        if reviews_count == 0:
            reviews_text_match = re.search(r'(\d+)\s*отзыв', page_text)
            if reviews_text_match:
                try:
                    reviews_count = int(reviews_text_match.group(1))
                except:
                    pass
       
        # Телефон
        phone = "Не указан"
        phone_elements = soup.find_all('a', href=re.compile(r'tel:'))
        if phone_elements:
            phone = phone_elements[0].text.strip()
       
        logger.info(f"✓ {name}")
        logger.info(f" Рейтинг: {rating}, Отзывов заявлено: {reviews_count}")
       
        # Собираем отзывы
        reviews = self.get_reviews(reviews_count)
       
        return Place(
            name=name,
            address=address,
            category=category,
            rating=rating,
            reviews_count=reviews_count,
            phone=phone,
            url=url,
            reviews=reviews
        )
   
    def decode_unicode_text(self, text: str) -> str:
        """Правильно декодирует юникод текст"""
        try:
            # Пробуем разные методы декодирования
            # Метод 1: Если текст уже в правильной кодировке
            if any(char in text for char in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'):
                return text
           
            # Метод 2: Стандартное декодирование unicode escape
            try:
                decoded = text.encode('utf-8').decode('unicode-escape')
                # Проверяем, что получилась кириллица
                if any(char in decoded for char in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'):
                    return decoded
            except:
                pass
           
            # Метод 3: Прямое декодирование как UTF-8
            try:
                decoded = text.encode('latin-1').decode('utf-8')
                if any(char in decoded for char in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'):
                    return decoded
            except:
                pass
           
            # Если ничего не помогло, возвращаем исходный текст
            return text
        except:
            return text
   
    def convert_russian_date(self, date_str: str) -> str:
        """Конвертирует русскую дату в формат YYYY-MM-DD"""
        months = {
            'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
            'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
            'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'
        }
       
        # Паттерн для русской даты: "11 августа 2024"
        for month_name, month_num in months.items():
            if month_name in date_str:
                parts = date_str.split()
                for i, part in enumerate(parts):
                    if part == month_name:
                        if i > 0 and i < len(parts) - 1:
                            day = parts[i-1].zfill(2)
                            year = parts[i+1]
                            if len(year) == 4:
                                return f"{year}-{month_num}-{day}"
        return date_str
   
    def extract_review_data(self, text_block: str) -> Optional[Dict]:
        """Извлекает данные отзыва из текстового блока"""
        try:
            # Ищем текст отзыва
            text_match = re.search(r'"text":\s*"([^"]+)"', text_block)
            if not text_match:
                return None
            
            text = self.decode_unicode_text(text_match.group(1))
            
            # Фильтрация текста: исключаем URL и короткие строки
            if len(text) < 30 or re.search(r'https?://|wa.me|instagram\.com', text) or any(stop in text.lower() for stop in self.stop_words):
                return None
            
            # Ищем автора
            author = "Пользователь 2GIS"
            author_patterns = [
                r'"userName":\s*"([^"]+)"',
                r'"authorName":\s*"([^"]+)"',
                r'"name":\s*"([^"]+)"',
                r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+'  # Дополнительный паттерн для имен
            ]
            for pattern in author_patterns:
                author_match = re.search(pattern, text_block)
                if author_match:
                    author = self.decode_unicode_text(author_match.group(1))
                    break
            
            # Ищем количество отзывов автора
            author_reviews_count = 0
            reviews_count_patterns = [
                r'"userReviewsCount":\s*(\d+)',
                r'"reviewsCount":\s*(\d+)',
                r'(\d+)\s*отзыв(?:ов)?'  # Добавляем поддержку "X отзывов"
            ]
            for pattern in reviews_count_patterns:
                count_match = re.search(pattern, text_block)
                if count_match:
                    author_reviews_count = int(count_match.group(1))
                    break
            
            # Ищем рейтинг
            rating = 5.0
            rating_match = re.search(r'"rating":\s*(\d+\.?\d*)', text_block)
            if rating_match:
                rating = float(rating_match.group(1))
            
            # Ищем дату
            date = ""
            date_patterns = [
                r'"dateEdited":\s*"([^"]*)"',
                r'"date":\s*"([^"]*)"',
                r'"createdAt":\s*"([^"]*)"',
                r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})'
            ]
            for pattern in date_patterns:
                date_match = re.search(pattern, text_block)
                if date_match:
                    date_raw = date_match.group(1) if 'T' in date_match.group(0) else date_match.group(0)
                    if 'T' in date_raw:
                        date = date_raw.split('T')[0]
                    else:
                        date = self.convert_russian_date(date_raw)
                    break
            
            return {
                'text': text,
                'author': author,
                'author_reviews_count': author_reviews_count,
                'rating': rating,
                'date': date
            }
        except:
            return None
   
    def get_reviews(self, total_count: int, max_reviews: int = 50) -> List[Review]:
        """Сбор отзывов с комбинированным подходом"""
        if total_count == 0:
            logger.info(" ℹ️ Отзывов нет")
            return []
        
        reviews = []
        
        # Стоп-слова для фильтрации мусора
        self.stop_words = [
            'cookie', 'политик', 'согласие', 'навигация', 'написать в whatsapp',
            'филиал', 'все филиалы', 'с ответами', 'положительные', 'отрицательные',
            'все отзывы', 'сервис персонал еда', 'выбран компанией', 'читать целиком',
            'полезно?', 'официальный ответ', 'сохранить', 'отправить', 'проехать',
            'реклама', 'скидка', 'подробнее по т.', 'оценки', 'оценка', 'отзывов',
            'меню', 'контакты', 'инфо', 'отзывы', 'оцените и оставьте отзыв',
            'добрый день', 'здравствуйте', 'благодарим', 'спасибо за', 'рады сотрудничать'
        ]
        
        try:
            # Переходим на вкладку отзывов
            current_url = self.driver.current_url
            reviews_url = current_url.split('?')[0] + '/tab/reviews'
            
            logger.info(f" 📝 Загрузка отзывов...")
            self.driver.get(reviews_url)
            time.sleep(5)
            
            # Прокручиваем для загрузки большего количества отзывов
            scroll_count = min(5, max_reviews // 10)
            for i in range(scroll_count):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            page_source = self.driver.page_source

            # Сохраняем HTML для отладки
            with open('debug_reviews.html', 'w', encoding='utf-8') as f:
                f.write(page_source)
            print("💾 HTML сохранен в debug_reviews.html для отладки")

            # МЕТОД 1: Поиск отзывов по уникальному маркеру "id":"...", "is_rated":true
            # Это гарантирует что мы находим именно отзывы, а не другие объекты с rating
            review_id_pattern = r'"id":"(\d+)","is_hidden":false,"is_rated":true'
            review_id_matches = list(re.finditer(review_id_pattern, page_source))

            logger.info(f" 🔍 Найдено {len(review_id_matches)} отзывов по ID")

            # Обрабатываем каждый отзыв
            for i, id_match in enumerate(review_id_matches[:max_reviews]):
                if len(reviews) >= max_reviews:
                    break

                try:
                    review_id = id_match.group(1)
                    match_pos = id_match.start()

                    # Берем ОЧЕНЬ ШИРОКИЙ контекст для этого отзыва (5000 символов до и 3000 после)
                    # Это должно захватить весь объект отзыва с date_created, user, rating, text
                    context_start = max(0, match_pos - 5000)
                    context_end = min(len(page_source), match_pos + 3000)
                    context = page_source[context_start:context_end]

                    # Ищем date_created ПЕРЕД id (расширяем поиск до 800 символов)
                    date = ""
                    date_pattern = r'"date_created":\s*"([^"]+T[^"]+)".{0,800}?"id":"' + re.escape(review_id) + r'"'
                    date_match = re.search(date_pattern, page_source[context_start:context_end], re.DOTALL)
                    if date_match:
                        date_raw = date_match.group(1)
                        date = date_raw.split('T')[0]
                    else:
                        # Если не нашли, попробуем извлечь дату из самого текста отзыва
                        # Ищем русские даты типа "15 июня"
                        text_date_match = re.search(r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)', context_after)
                        if text_date_match:
                            # Конвертируем русскую дату
                            date = self.convert_russian_date(text_date_match.group(0) + ' 2024')  # Предполагаем 2024 год

                    # Ищем rating ПОСЛЕ id
                    context_after = context[match_pos - context_start:]
                    rating = 5.0
                    rating_match = re.search(r'"rating":\s*(\d)', context_after)
                    if rating_match:
                        rating = float(rating_match.group(1))

                    # Ищем text ПОСЛЕ id
                    text_match = re.search(r'"text":\s*"([^"]{30,})"', context_after)
                    if not text_match:
                        continue

                    text = self.decode_unicode_text(text_match.group(1))
                    if any(stop in text.lower() for stop in self.stop_words):
                        continue

                    # Ищем user.name ПОСЛЕ id (user идет после rating и text)
                    author = "Пользователь 2GIS"
                    user_name_match = re.search(r'"user":\s*\{.{0,1500}?"name":\s*"([^"]+)"', context_after, re.DOTALL)
                    if user_name_match:
                        potential_author = self.decode_unicode_text(user_name_match.group(1))
                        if potential_author and len(potential_author) > 2:
                            author = potential_author

                    # Ищем user.reviews_count ПОСЛЕ id
                    author_reviews_count = 0
                    reviews_count_match = re.search(r'"user":\s*\{.{0,1500}?"reviews_count":\s*(\d+)', context_after, re.DOTALL)
                    if reviews_count_match:
                        author_reviews_count = int(reviews_count_match.group(1))

                    reviews.append(Review(
                        author=author,
                        author_reviews_count=author_reviews_count,
                        rating=rating,
                        text=text[:500],
                        date=date
                    ))

                    logger.debug(f"✓ Отзыв #{review_id}: {author} ({author_reviews_count} отз.) - {rating}★ [{date}]")

                except Exception as e:
                    logger.debug(f"Ошибка обработки отзыва {i}: {e}")
                    continue
            
            if len(reviews) < 5:
                text_pattern = r'"text":\s*"([^"]{30,1500})"'
                text_matches = list(re.finditer(text_pattern, page_source))
                logger.info(f" 🔍 Найдено {len(text_matches)} потенциальных отзывов")
                
                for match in text_matches:
                    if len(reviews) >= max_reviews:
                        break
                    
                    try:
                        text = self.decode_unicode_text(match.group(1))
                        text_lower = text.lower()
                        if any(stop in text_lower for stop in self.stop_words) or 'официальный ответ' in text_lower or 'добрый день' in text_lower or len(text.split()) < 5:
                            continue
                        
                        context_start = max(0, match.start() - 500)
                        context_end = min(len(page_source), match.end() + 500)
                        context = page_source[context_start:context_end]
                        
                        author = "Пользователь 2GIS"
                        # Ищем имя автора в разных полях JSON
                        for author_field in ['"userName"', '"authorName"', '"name"', '"user"']:
                            author_match = re.search(f'{author_field}:\\s*"([^"]+)"', context)
                            if author_match:
                                potential_author = self.decode_unicode_text(author_match.group(1))
                                if potential_author and len(potential_author) > 2 and not any(word in potential_author.lower() for word in ['user', '2gis', 'anonymous']):
                                    author = potential_author
                                    break
                        
                        author_reviews_count = 0
                        # Ищем количество отзывов автора в JSON полях
                        for count_field in ['"userReviewsCount"', '"reviewsCount"', '"totalReviews"']:
                            user_reviews_match = re.search(f'{count_field}:\\s*(\\d+)', context)
                            if user_reviews_match:
                                author_reviews_count = int(user_reviews_match.group(1))
                                break
                        # Если не нашли в JSON, ищем текстовый паттерн
                        if author_reviews_count == 0:
                            count_match = re.search(r'(\\d+)\\s*отзыв', context)
                            if count_match:
                                author_reviews_count = int(count_match.group(1))
                        
                        rating = 5.0
                        rating_match = re.search(r'"rating":\s*(\d+)', context)
                        if rating_match:
                            rating = float(rating_match.group(1))
                        
                        date = ""
                        # Приоритет русской дате
                        russian_date_match = re.search(r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})', context)
                        if russian_date_match:
                            date = self.convert_russian_date(russian_date_match.group(0))
                        else:
                            # Ищем дату в JSON полях
                            for pattern in [r'"visitDate":\s*"([^"]*)"', r'"dateEdited":\s*"([^"]*)"', r'"date":\s*"([^"]*)"', r'"createdAt":\s*"([^"]*)"', r'"timestamp":\s*"([^"]*)"']:
                                date_match = re.search(pattern, context)
                                if date_match:
                                    date_raw = date_match.group(1)
                                    if 'T' in date_raw:
                                        date = date_raw.split('T')[0]
                                    elif len(date_raw) >= 10 and date_raw[0].isdigit():
                                        date = date_raw[:10]
                                    if date:  # Если нашли валидную дату, выходим
                                        break
                        
                        reviews.append(Review(
                            author=author,
                            author_reviews_count=author_reviews_count,
                            rating=rating,
                            text=text[:500],
                            date=date
                        ))
                    except Exception as e:
                        logger.debug(f"Ошибка обработки отзыва: {e}")
                        continue
            
            if len(reviews) < 10:
                logger.info(" 🔍 Поиск отзывов через Selenium селекторы...")
                try:
                    time.sleep(2)
                    review_selectors = [
                        'div[class*="reviewItem"]',
                        'div[class*="review__container"]',
                        'article[class*="review"]',
                        'div[data-type="review"]',
                        'div[class*="card"][class*="review"]'
                    ]
                    
                    for selector in review_selectors:
                        review_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if review_elements:
                            logger.info(f" ✓ Найдено {len(review_elements)} элементов по селектору: {selector}")
                            for element in review_elements[:max_reviews - len(reviews)]:
                                try:
                                    element_html = element.get_attribute('outerHTML')
                                    element_text = element.text.split('\n')
                                    
                                    review_text = ""
                                    author = "Пользователь 2GIS"
                                    date = ""
                                    author_reviews = 0
                                    rating = 5.0
                                    
                                    for line in element_text:
                                        if len(line) > 50 and not review_text and not re.search(r'https?://', line):
                                            review_text = line
                                        if re.search(r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+', line):
                                            author = line.strip()
                                        if re.search(r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})', line):
                                            date = self.convert_russian_date(line)
                                        if 'отзыв' in line:
                                            count_match = re.search(r'(\d+)\s*отзыв', line)
                                            if count_match:
                                                author_reviews = int(count_match.group(1))
                                        rating_match = re.search(r'star.*?(\d)', element_html.lower())
                                        if rating_match:
                                            rating = float(rating_match.group(1))
                                    
                                    if review_text and len(review_text) > 30:
                                        reviews.append(Review(
                                            author=author,
                                            author_reviews_count=author_reviews,
                                            rating=rating,
                                            text=review_text[:500],
                                            date=date
                                        ))
                                except Exception as e:
                                    logger.debug(f"Ошибка обработки элемента: {e}")
                                    continue
                            if len(reviews) > 0:
                                break
                except Exception as e:
                    logger.error(f"Ошибка Selenium поиска: {e}")
            
            if len(reviews) > 0:
                need_dates = not any(r.date for r in reviews)
                need_names = all(r.author == "Пользователь 2GIS" for r in reviews)
                
                if need_dates or need_names:
                    logger.info(" 🔍 Дополнительный поиск дат и имен в HTML...")
                    russian_dates = re.findall(
                        r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})',
                        page_source
                    )
                    name_pattern = r'([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)'
                    potential_names = re.findall(name_pattern, page_source)
                    service_words = ['Отзывы', 'Контакты', 'Меню', 'Информация', 'Написать', 'Ответить',
                                    'Полезно', 'Официальный', 'Компания', 'Выбран', 'Адрес', 'Телефон']
                    valid_names = [name for name in potential_names if not any(word in name for word in service_words)]
                    reviews_counts = re.findall(r'(\d+)\s*отзыв', page_source)
                    
                    # Associate data with reviews based on order and context
                    for i, review in enumerate(reviews):
                        if not review.date and i < len(russian_dates):
                            full_date = f"{russian_dates[i][0]} {russian_dates[i][1]} {russian_dates[i][2]}"
                            review.date = self.convert_russian_date(full_date)
                        if review.author == "Пользователь 2GIS" and i < len(valid_names):
                            review.author = valid_names[i]
                        if review.author_reviews_count == 0 and i < len(reviews_counts):
                            try:
                                # Only update if the count matches the author's context
                                if i < len(review_elements) and review_elements[i].text.find(valid_names[i]) >= 0:
                                    review.author_reviews_count = int(reviews_counts[i])
                            except:
                                pass
            
            unique_reviews = []
            seen_texts = set()
            for review in reviews:
                normalized = review.text.lower().strip()[:100]
                if normalized not in seen_texts and len(review.text) >= 30:
                    seen_texts.add(normalized)
                    unique_reviews.append(review)
            
            if unique_reviews:
                ratings_stats = {}
                dates_count = 0
                for r in unique_reviews:
                    ratings_stats[r.rating] = ratings_stats.get(r.rating, 0) + 1
                    if r.date:
                        dates_count += 1
                logger.info(f" ✅ Собрано {len(unique_reviews)} отзывов. Рейтинги: {ratings_stats}, С датами: {dates_count}")
                for r in unique_reviews[:5]:
                    if r.date:
                        logger.debug(f" Пример отзыва с датой: {r.author} - {r.date}")
                        break
            else:
                logger.info(f" ⚠️ Отзывы не найдены")
            
            return unique_reviews
        
        except Exception as e:
            logger.error(f" ❌ Ошибка при сборе отзывов: {e}")
            import traceback
            traceback.print_exc()
            return []
   
    def scrape_category(self, query: str, city: str = "almaty", max_places: int = 10) -> List[Place]:
        """Парсинг категории"""
        urls = self.search_places(query, city, max_places)
       
        if not urls:
            logger.error("❌ Заведения не найдены")
            return []
       
        places = []
       
        for i, url in enumerate(urls, 1):
            logger.info(f"\n{'='*70}")
            logger.info(f"[{i}/{len(urls)}]")
           
            try:
                place = self.get_place_data(url)
                places.append(place)
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
                import traceback
                traceback.print_exc()
           
            # Задержка между запросами
            time.sleep(random.uniform(3, 5))
       
        logger.info(f"\n{'='*70}")
        logger.info(f"🎉 ИТОГО: {len(places)} заведений")
        total_reviews = sum(len(p.reviews) for p in places)
        logger.info(f"💬 Всего отзывов: {total_reviews}")
       
        return places
   
    def save_to_json(self, places: List[Place], filename: str):
        """Сохранение в JSON"""
        data = [asdict(place) for place in places]
       
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
       
        logger.info(f"\n💾 Данные сохранены в {filename}")
   
    def close(self):
        """Закрытие браузера"""
        self.driver.quit()
        logger.info("👋 Готово!")
# ===================================================================
# ЗАПУСК
# ===================================================================
if __name__ == "__main__":
    import sys
    import io
    # Фикс кодировки для Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 70)
    print("🚀 ПАРСЕР 2GIS - Финальная версия")
    print("=" * 70)
    print()
   
    scraper = SimpleTwoGISScraper(headless=False)
   
    try:
        places = scraper.scrape_category(
            query="кофейни",
            city="almaty",
            max_places=1
        )
       
        if places:
            print("\n" + "=" * 70)
            print("📊 РЕЗУЛЬТАТЫ")
            print("=" * 70)
           
            for i, place in enumerate(places, 1):
                print(f"\n{i}. {place.name}")
                print(f" 📍 {place.address}")
                print(f" 📂 {place.category}")
                print(f" ⭐ {place.rating} ({place.reviews_count} отзывов)")
                print(f" 📞 {place.phone}")
                print(f" 💬 Собрано отзывов: {len(place.reviews)}")
               
                if place.reviews:
                    print(f"\n 📝 Примеры отзывов:")
                    for j, review in enumerate(place.reviews[:3], 1):
                        rating_str = f"⭐{review.rating}" if review.rating else "⭐?"
                        date_str = f" [{review.date}]" if review.date else ""
                        reviews_str = f" ({review.author_reviews_count} отз.)" if review.author_reviews_count else ""
                        print(f" {j}. {review.author}{reviews_str} {rating_str}{date_str}")
                        print(f" \"{review.text[:100]}...\"")
           
            scraper.save_to_json(places, "2gis_result.json")
           
            print("\n" + "=" * 70)
            print("✅ ГОТОВО! Проверьте файл: 2gis_result.json")
            print("=" * 70)
        else:
            print("\n❌ Данные не собраны")
       
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
   
    finally:
        scraper.close()