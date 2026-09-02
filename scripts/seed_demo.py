"""演示数据种子脚本。

用法：python -m scripts.seed_demo

创建可重复演示的会话与消息数据，覆盖核心场景：
1. 医院导诊（ASR + RAG + 路线 Widget）
2. 政务服务（社保查询 + 翻译）
3. 听障模式（高对比度字幕 + 慢速播报）
4. 老年模式（大字体 + 重复确认）
"""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger, setup_logging
from app.models.database import async_session_factory, init_db
from app.repositories.session_repo import MessageRepository, SessionRepository

logger = get_logger()

# 演示话术
DEMO_SCENARIOS = [
    {
        "title": "医院导诊-骨科问路",
        "scene": "hospital",
        "mode": "standard",
        "messages": [
            ("staff", "请问骨科在哪里", "transcript"),
            ("assistant", "骨科在 2 楼外科区东侧。从大厅入口出发，乘电梯到 2 楼，向东前行约 50 米即可到达。", "text"),
        ],
    },
    {
        "title": "医院导诊-急诊路线",
        "scene": "hospital",
        "mode": "hearing",
        "messages": [
            ("staff", "急诊怎么走", "transcript"),
            ("assistant", "急诊在 1 楼西侧。从大厅入口出发，向西前行约 30 米即可到达急诊入口。", "text"),
        ],
    },
    {
        "title": "政务-社保卡申领翻译",
        "scene": "government",
        "mode": "standard",
        "messages": [
            ("staff", "社保卡怎么办", "transcript"),
            ("assistant", "社保卡申领流程：1. 携带身份证到社保窗口；2. 填写申领表；3. 缴纳工本费；4. 7 个工作日后领取。", "text"),
            ("staff", "翻译成英文", "text"),
            ("assistant", "翻译结果：Social Security Card application: 1. Bring ID Card to the Social Security window; 2. Fill in the application form; 3. Pay the fee; 4. Collect in 7 working days.", "text"),
        ],
    },
    {
        "title": "适老化-挂号流程",
        "scene": "hospital",
        "mode": "elderly",
        "messages": [
            ("staff", "我想挂号", "transcript"),
            ("assistant", "您好！挂号在一楼大厅中部。请携带身份证或社保卡到挂号窗口，工作人员会帮您办理。", "text"),
        ],
    },
]


async def seed() -> None:
    setup_logging()
    await init_db()
    logger.info("开始注入演示数据…")

    async with async_session_factory() as db:
        session_repo = SessionRepository(db)
        msg_repo = MessageRepository(db)

        for scenario in DEMO_SCENARIOS:
            session = await session_repo.create(
                scene=scenario["scene"],
                mode=scenario["mode"],
            )
            for role, content, msg_type in scenario["messages"]:
                await msg_repo.add(
                    session_id=session.id,
                    role=role,
                    content=content,
                    speaker="staff" if role == "staff" else "assistant",
                    message_type=msg_type,
                )
            logger.info("注入演示会话：{} ({})", scenario["title"], session.id)

        await db.commit()

    logger.info("演示数据注入完成，共 {} 个场景", len(DEMO_SCENARIOS))


if __name__ == "__main__":
    asyncio.run(seed())
