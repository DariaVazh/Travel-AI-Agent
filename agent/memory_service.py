from database.user_repository import (
    get_user_memory,
    update_user_memory
)

# Для даши
async def extract_memory_changes(messages: list[dict], old_memory: dict) -> dict:
    ...


async def checkpoint_memory(agent, telegram_id: int) -> None:
    end_index = len(agent.chat_history)

    messages = agent.chat_history[
        agent.memory_saved_upto:end_index
    ]

    if not messages:
        return

    # Получаем старую память из PostgreSQL
    old_memory = await get_user_memory(telegram_id)

    # LLM возвращает изменения памяти надо реализовать даше
    changes = await extract_memory_changes(
        messages=messages,
        old_memory=old_memory
    )

    if changes:
        await update_user_memory(
            telegram_id=telegram_id,
            changes=changes
        )

    agent.long_term_memory = await get_user_memory(
        telegram_id
    )

    agent.memory_saved_upto = end_index
