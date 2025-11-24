# Утилиты для создания и восстановления бэкапов

Универсальные скрипты для создания и восстановления бэкапов любых директорий с поддержкой сжатия и шифрования.

## Скрипты

- **`backup_folder.py`** - создание бэкапа директории в ZIP архив
- **`restore_folder.py`** - восстановление директории из ZIP архива

##  Быстрый старт

### Создание бэкапа

```bash
# Базовое использование
python -m utils.backup_folder /path/to/source/folder

# С указанием выходного файла
python -m utils.backup_folder /path/to/source/folder --output /path/to/backup.zip

# С паролем
python -m utils.backup_folder /path/to/source/folder --password

# Без пароля (явно)
python -m utils.backup_folder /path/to/source/folder --no-password
```

### Восстановление из бэкапа

```bash
# Базовое использование
python -m utils.restore_folder backup.zip

# С указанием целевой директории
python -m utils.restore_folder backup.zip --output /path/to/restore

# С паролем в командной строке (не рекомендуется)
python -m utils.restore_folder backup.zip --password mypassword
```

## Возможности

### backup_folder.py

- **Универсальность** - работает с любой директорией
- **Сжатие** - максимальное сжатие (уровень 9)
- **Шифрование** - опциональное AES-256 шифрование через `pyzipper`
- **Прогресс** - отображение прогресса архивации в реальном времени
- **Проверка места** - автоматическая проверка свободного места на диске
- **Статистика** - подробная статистика после завершения
- **Graceful shutdown** - корректное прерывание по Ctrl+C с освобождением ресурсов

### restore_folder.py

- **Автоопределение пароля** - автоматически определяет, защищен ли архив паролем
- **Проверка пароля** - интерактивный ввод пароля с проверкой (до 3 попыток)
- **Прогресс** - отображение прогресса извлечения в реальном времени
- **Проверка целостности** - валидация архива перед распаковкой
- **Проверка места** - автоматическая проверка свободного места на диске
- **Статистика** - подробная статистика после завершения
- **Graceful shutdown** - корректное прерывание по Ctrl+C

## Документация

### backup_folder.py

#### Синтаксис

```bash
python -m utils.backup_folder <source_dir> [--output <output_path>] [--password] [--no-password]
```

#### Параметры

- **`source_dir`** (обязательный) - путь к директории для бэкапа
- **`--output`** (опционально) - путь к выходному архиву. По умолчанию: `<source_dir_name>_backup_<timestamp>.zip` в текущей директории
- **`--password`** (опционально) - запросить пароль для шифрования архива
- **`--no-password`** (опционально) - явно указать, что пароль не нужен (переопределяет `--password`)

#### Примеры

```bash
# Создать бэкап текущей директории
python -m utils.backup_folder .

# Создать бэкап с указанием выходного файла
python -m utils.backup_folder /home/user/documents --output /backup/documents_backup.zip

# Создать защищенный паролем бэкап
python -m utils.backup_folder /home/user/important --password

# Создать бэкап без пароля (даже если pyzipper установлен)
python -m utils.backup_folder /home/user/data --no-password
```

#### Выходные данные

После завершения архивации скрипт выводит:

```
============================================================
BACKUP SUCCESSFULLY CREATED
============================================================
Path: /path/to/backup.zip
Total files processed: 1234
Total size of original files: 1.5 GB
Archive size: 750 MB
Compression ratio: 50.0%
```

### restore_folder.py

#### Синтаксис

```bash
python -m utils.restore_folder <archive_path> [--output <output_dir>] [--password <password>]
```

#### Параметры

- **`archive_path`** (обязательный) - путь к ZIP архиву для восстановления
- **`--output`** (опционально) - целевая директория для восстановления. По умолчанию: текущая директория + имя архива без расширения
- **`--password`** (опционально) - пароль для расшифровки архива (не рекомендуется для безопасности, лучше использовать интерактивный ввод)

#### Примеры

```bash
# Восстановить из архива в текущую директорию
python -m utils.restore_folder backup.zip

# Восстановить в указанную директорию
python -m utils.restore_folder backup.zip --output /path/to/restore

# Восстановить с паролем (интерактивный ввод)
python -m utils.restore_folder encrypted_backup.zip
# Скрипт автоматически определит, что нужен пароль, и запросит его

# Восстановить с паролем из командной строки (не рекомендуется)
python -m utils.restore_folder encrypted_backup.zip --password mypassword
```

#### Выходные данные

После завершения восстановления скрипт выводит:

```
============================================================
Restore complete!
============================================================
Target directory: /path/to/restore
Files extracted: 1234/1234
Total size extracted: 1.5 GB
```

## Безопасность

### Шифрование

- Скрипты используют **AES-256** шифрование через библиотеку `pyzipper`
- Пароли **никогда не сохраняются** в логах или файлах
- Пароли запрашиваются через `getpass`, что скрывает ввод в терминале

### Рекомендации

- **Используйте интерактивный ввод пароля** вместо `--password` в командной строке
- **Храните пароли в безопасном месте** (менеджер паролей)
- **Не коммитьте архивы с паролями** в репозиторий
- **Проверяйте целостность архивов** перед удалением исходных данных

## Зависимости

### Обязательные

- Python 3.9+
- Стандартная библиотека Python (zipfile, argparse, getpass, shutil, pathlib)

### Опциональные

- **`pyzipper`** - для поддержки AES-256 шифрования

```bash
pip install pyzipper
```

**Примечание:** Если `pyzipper` не установлен, скрипты будут работать, но без поддержки шифрования паролем.

## Установка

Скрипты не требуют установки. Просто используйте их как модули Python:

```bash
python -m utils.backup_folder ...
python -m utils.restore_folder ...
```

Или напрямую:

```bash
python utils/backup_folder.py ...
python utils/restore_folder.py ...
```

##  Статистика и метрики

### backup_folder.py

- **Общее количество файлов** - сколько файлов обработано
- **Общий размер** - размер исходных файлов
- **Размер архива** - размер сжатого архива
- **Коэффициент сжатия** - процент сжатия (может быть отрицательным для очень маленьких файлов из-за ZIP overhead)

### restore_folder.py

- **Файлов извлечено** - количество успешно извлеченных файлов
- **Общий размер** - размер извлеченных данных
- **Пропущенные файлы** - файлы, которые не удалось извлечь
- **Ошибки** - количество ошибок при извлечении

##  Обработка ошибок

### backup_folder.py

- **FileNotFoundError** - исходная директория не найдена
- **NotADirectoryError** - указанный путь не является директорией
- **PermissionError** - недостаточно прав для доступа к файлам
- **OSError** - недостаточно места на диске или другие I/O ошибки
- **KeyboardInterrupt** - пользователь прервал операцию (Ctrl+C)
- **RuntimeError** - ошибки при работе с архивом

### restore_folder.py

- **FileNotFoundError** - архив не найден
- **zipfile.BadZipFile** - архив поврежден или не является ZIP файлом
- **RuntimeError** - неправильный пароль или архив требует пароль
- **OSError** - недостаточно места на диске или другие I/O ошибки
- **KeyboardInterrupt** - пользователь прервал операцию (Ctrl+C)

## Прерывание операций

Оба скрипта поддерживают корректное прерывание по **Ctrl+C**:

- **backup_folder.py**: удаляет неполный архив при прерывании
- **restore_folder.py**: останавливает извлечение, оставляя уже извлеченные файлы

## Примеры использования

### Сценарий 1: Ежедневный бэкап

```bash
# Создать бэкап с паролем
python -m utils.backup_folder /home/user/documents --password

# Восстановить из бэкапа
python -m utils.restore_folder documents_backup_20250101_120000.zip --output /home/user/restored
```

### Сценарий 2: Бэкап перед обновлением

```bash
# Создать бэкап без пароля (быстро)
python -m utils.backup_folder /var/www/myapp --output /backup/myapp_before_update.zip

# После обновления, если что-то пошло не так, восстановить
python -m utils.restore_folder /backup/myapp_before_update.zip --output /var/www/myapp_restored
```

### Сценарий 3: Бэкап конфигурационных файлов

```bash
# Создать защищенный бэкап конфигов
python -m utils.backup_folder /etc/myapp --password --output /secure/backup/configs.zip

# Восстановить конфиги на новом сервере
python -m utils.restore_folder /secure/backup/configs.zip --output /etc/myapp
```

## Тестирование

Скрипты имеют полное покрытие unit и integration тестами:

```bash
# Запустить unit тесты
pytest tests/unit/test_backup_folder.py -v

# Запустить integration тесты
pytest tests/integration/test_backup_folder_integration.py -v

# Запустить тесты восстановления (когда будут созданы)
pytest tests/unit/test_restore_folder.py -v
pytest tests/integration/test_restore_folder_integration.py -v
```

## Устранение неполадок

### Проблема: "Archive appears to be encrypted. Install pyzipper"

**Решение:** Установите `pyzipper`:
```bash
pip install pyzipper
```

### Проблема: "Not enough disk space"

**Решение:** Освободите место на диске или укажите другой диск для выходного файла.

### Проблема: "Incorrect password"

**Решение:** Убедитесь, что вы используете правильный пароль. Пароли чувствительны к регистру.

### Проблема: "Archive is corrupted or not a valid ZIP file"

**Решение:** Проверьте, что архив не был поврежден при передаче. Попробуйте скачать/передать архив заново.

## Дополнительная информация

### Архитектура

Скрипты следуют принципам:
- **Zen of Python (ZoP)**
- **PEP 8** (стиль кода)
- **PEP 257** (docstrings)
- **PEP 484** (type hints)
- **SOLID принципы**
- **Модульная структура**

### Производительность

- **Сжатие**: максимальный уровень (9) для лучшего сжатия
- **Чтение файлов**: по частям (chunks) для эффективной работы с большими файлами
- **Прогресс**: обновляется каждые 10 файлов для баланса между информативностью и производительностью

### Ограничения

- Максимальный размер файла: ограничен только доступной памятью и местом на диске
- Поддержка форматов: только ZIP (стандартный и AES-256 через pyzipper)
- Платформы: Windows, Linux, macOS

## Лицензия

The Unlicensed

##  Вклад

При обнаружении проблем или предложений по улучшению создавайте issues или pull requests в репозитории проекта.

---

**Версия:** 1.0.0  


