# Автоматизатор тест-кейсов

Парсер тест-кейсов TestLink с автоматическим запуском на OpenQA

Система для автоматизации выполнения тест-кейсов из TestLink на платформе OpenQA.

## Структура проекта
```
testlink-openqa-automator/
├── src/
  ├── app/
     ├── api/                      # Эндпоинты
        ├── openqa.py   
        ├── testlink.py            # Эндпоинты, связанные с TestLink
     ├── integrations/
        ├── llm.py 
     ├── services/                 # Сервисы (логика)
        ├── openqa_runner.py       # Логика для работы с OpenQA (пока не реализовано)
        ├── testlink_sync.py       # Логика для получения тест-кейсов с TestLink и из базы данных
     ├── main.py                   
     ├── schemas.py                # Pydantic модели для fastapi
├── .env
├──  Dockerfile
├── docker-compose.yaml
├── poetry.lock
├── pyproject.toml
```

## 🚀 Быстрый запуск

### 1. Клонирование проекта
```bash
git clone https://github.com/AleksandrIvanov2004/testlink-openqa-automator.git
cd testlink-openqa-automator
```

### 2. Загрузка LLM-модели
```bash
docker run -d --name ollama ollama/ollama 
docker run -d \
  -v ollama:/root/.ollama \
  -v $(pwd):/data \
  -p 11435:11434 \
  --name ollama \
  ollama/ollama
docker exec ollama ollama pull deepseek-coder-v2:16b
```

### 3. Запуск проекта
```bash
docker buildx build --network=host -t app .
docker compose up app 
```

### 4. Реализованные эндпоинты
1. Получение тест-кейса по номеру с TestLink - http://localhost:8000/api/v1/testlink/sync/{testcase_number}
2. Генерация автотеста и запуск job'а на openQA - http://localhost:8000/api/v1/openqa/schedule-job/{testcase_number}/{branch}/{iso}
3. Генерация автотеста с помощью llm и запуск job'а на openQA - http://localhost:8000/api/v1/openqa/llm/schedule-job/{testcase_number}/{branch}/{iso}
