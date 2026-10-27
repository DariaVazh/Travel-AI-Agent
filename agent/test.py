from agent.agent import TravelAgent

def main():
    # Создаем экземпляр агента
    agent = TravelAgent(user_id="test_user")

    print("--- 1. Тестируем шутки и разговор не по делу ---")
    response = agent.handle("Привет! Как дела? Знаешь анекдот про колобка?")
    print(f"Агент: {response}\n")

    print("--- 2. Имитируем приход JSON-файла от внешней программы ---")
    # Создаем структуру, которую в будущем будет присылать другая программа
    mock_json_data = {
        "destination": {"city": "Сочи"},
        "packages": [
            {
                "title": "Эконом-вариант",
                "totals": {"grand": 32000, "currency": "RUB"},
                "hotel": {"name": "Бархатные сезоны", "stars": 3, "price_per_night": 3500},
                "transport": {"outbound": {"airline": "Utair", "flight_no": "UT-123", "price": 12000}},
                "warnings": ["Невозвратный тариф", "Далеко от моря"]
            },
            {
                "title": "Комфорт",
                "totals": {"grand": 65000, "currency": "RUB"},
                "hotel": {"name": "Swissôtel Resort Сочи Кэмелия", "stars": 5, "price_per_night": 15000},
                "transport": {"outbound": {"airline": "Aeroflot", "flight_no": "SU-1122", "price": 20000}},
                "warnings": []
            }
        ]
    }

    # Передаем эти данные агенту через метод интеграции
    agent.feed_external_routes(mock_json_data)
    print("[Система]: JSON с маршрутами успешно загружен в агента.\n")

    print("--- 3. Проверяем, как агент очеловечивает данные ---")
    response = agent.handle("Расскажи, что у нас есть по Сочи, какие варианты?")
    print(f"Агент:\n{response}\n")

    print("--- 4. Проверяем улучшенную память (контекст диалога) ---")
    response = agent.handle("А какой из них дешевле?")
    print(f"Агент:\n{response}\n")

if __name__ == "__main__":
    main()