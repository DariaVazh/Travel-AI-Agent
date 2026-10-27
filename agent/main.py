from agent import TravelAgent


def main():
    print("Travel Agent (OpenRouter). Пустая строка — выход.")
    print("Примеры: «хочу к морю в ноябре недорого с ребёнком» / «дешевле» / «оформить»\n")
    agent = TravelAgent()
    while True:
        try:
            user = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            break
        try:
            answer = agent.handle(user)
        except Exception as e:
            answer = f"[ошибка] {e}"
        print(f"Агент: {answer}\n")


if __name__ == "__main__":
    main()
