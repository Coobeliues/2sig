"""
Скрипт для автоматической настройки окружения
"""

import subprocess
import sys
import os
from pathlib import Path


def print_header(text):
    """Красивый заголовок"""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80 + "\n")


def run_command(command, description):
    """Выполнение команды с выводом прогресса"""
    print(f"⏳ {description}...")
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✅ {description} - успешно!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при {description}:")
        print(e.stderr)
        return False


def check_python_version():
    """Проверка версии Python"""
    print_header("Проверка Python")

    version = sys.version_info
    print(f"Текущая версия Python: {version.major}.{version.minor}.{version.micro}")

    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Требуется Python 3.8 или выше!")
        return False

    print("✅ Версия Python подходит")
    return True


def create_directories():
    """Создание необходимых директорий"""
    print_header("Создание директорий")

    directories = ['cache', 'models', 'logs']

    for dir_name in directories:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            dir_path.mkdir(parents=True)
            print(f"✅ Создана директория: {dir_name}")
        else:
            print(f"ℹ️  Директория уже существует: {dir_name}")

    return True


def install_requirements():
    """Установка зависимостей из requirements.txt"""
    print_header("Установка зависимостей")

    if not Path('requirements.txt').exists():
        print("❌ Файл requirements.txt не найден!")
        return False

    # Обновление pip
    run_command(
        f"{sys.executable} -m pip install --upgrade pip",
        "Обновление pip"
    )

    # Установка зависимостей
    return run_command(
        f"{sys.executable} -m pip install -r requirements.txt",
        "Установка библиотек из requirements.txt"
    )


def download_spacy_model():
    """Скачивание spaCy модели для русского языка"""
    print_header("Установка spaCy модели")

    return run_command(
        f"{sys.executable} -m spacy download ru_core_news_sm",
        "Скачивание ru_core_news_sm"
    )


def check_data_files():
    """Проверка наличия необходимых файлов данных"""
    print_header("Проверка файлов данных")

    required_files = ['reviews_full.csv', 'places.csv']
    all_exist = True

    for filename in required_files:
        if Path(filename).exists():
            size = Path(filename).stat().st_size / (1024 * 1024)  # MB
            print(f"✅ {filename} найден ({size:.2f} MB)")
        else:
            print(f"⚠️  {filename} не найден")
            all_exist = False

    if not all_exist:
        print("\n⚠️  Некоторые файлы данных отсутствуют.")
        print("Убедитесь, что у вас есть файлы reviews_full.csv и places.csv")

    return all_exist


def test_imports():
    """Тестирование импорта основных библиотек"""
    print_header("Тестирование импорта библиотек")

    libraries = [
        ('pandas', 'pandas'),
        ('numpy', 'numpy'),
        ('sentence_transformers', 'sentence-transformers'),
        ('faiss', 'faiss-cpu'),
        ('streamlit', 'streamlit'),
        ('spacy', 'spacy'),
    ]

    all_ok = True

    for module_name, package_name in libraries:
        try:
            __import__(module_name)
            print(f"✅ {package_name} импортирован успешно")
        except ImportError:
            print(f"❌ Не удалось импортировать {package_name}")
            all_ok = False

    return all_ok


def create_config():
    """Создание файла конфигурации"""
    print_header("Создание конфигурации")

    config_content = """# Конфигурация проекта

# Пути к данным
REVIEWS_PATH = 'reviews_full.csv'
PLACES_PATH = 'places.csv'

# Пути для кэша
EMBEDDINGS_CACHE = 'cache/embeddings.pkl'
MODEL_CACHE = 'cache/models'

# Параметры модели
MODEL_NAME = 'sentence-transformers/LaBSE'  # или 'DeepPavlov/rubert-base-cased-sentence'
BATCH_SIZE = 32
USE_GPU = False

# Параметры поиска
DEFAULT_TOP_K = 10
MIN_REVIEWS = 3
AGGREGATION_METHOD = 'weighted'  # 'mean', 'max', 'weighted'

# Streamlit настройки
STREAMLIT_PORT = 8501
STREAMLIT_HOST = 'localhost'
"""

    config_path = Path('config.py')
    if not config_path.exists():
        config_path.write_text(config_content)
        print("✅ Создан файл config.py")
    else:
        print("ℹ️  Файл config.py уже существует")

    return True


def print_next_steps():
    """Вывод следующих шагов"""
    print_header("Установка завершена!")

    print("""
🎉 Поздравляем! Окружение настроено.

📝 Следующие шаги:

1. Запустите базовый поиск:
   python semantic_search.py

2. Или запустите веб-интерфейс:
   streamlit run app.py

3. Или посмотрите примеры:
   python examples.py

📚 Полезные ссылки:
- Быстрый старт: QUICK_START.md
- Детальный план: PROJECT_ROADMAP.md
- Документация: README.md

💡 Подсказки:
- При первом запуске будут созданы эмбеддинги (может занять 5-15 минут)
- Эмбеддинги сохраняются в cache/ для быстрой загрузки в будущем
- Для GPU ускорения установите faiss-gpu и PyTorch с CUDA

Удачи! 🚀
""")


def main():
    """Основная функция установки"""
    print_header("Настройка окружения для проекта NLP 2GIS")

    steps = [
        ("Проверка Python", check_python_version),
        ("Создание директорий", create_directories),
        ("Установка зависимостей", install_requirements),
        ("Скачивание spaCy модели", download_spacy_model),
        ("Проверка файлов данных", check_data_files),
        ("Тестирование импортов", test_imports),
        ("Создание конфигурации", create_config),
    ]

    results = []

    for step_name, step_func in steps:
        try:
            success = step_func()
            results.append((step_name, success))
        except Exception as e:
            print(f"❌ Ошибка в шаге '{step_name}': {e}")
            results.append((step_name, False))

    # Итоги
    print_header("Итоги установки")

    all_success = True
    for step_name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {step_name}")
        if not success:
            all_success = False

    if all_success:
        print_next_steps()
    else:
        print("\n⚠️  Некоторые шаги завершились с ошибками.")
        print("Проверьте логи выше и исправьте проблемы.")
        print("Затем запустите установку снова.")


if __name__ == "__main__":
    main()
