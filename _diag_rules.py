import asyncio, sys
sys.path.insert(0, "admin-api")
sys.path.insert(0, "shared/src")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.infrastructure.repositories.models import RuleModel

URL = "mysql+asyncmy://root:Hell0world!@192.168.0.110:3306/fangyu_v2"


async def main() -> None:
    engine = create_async_engine(URL)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        rows = (await s.execute(select(RuleModel).limit(3))).scalars().all()
        for r in rows:
            print("id", r.id)
            print("  conditions type:", type(r.conditions), repr(r.conditions)[:120])
            print("  tags type:", type(r.tags), repr(r.tags)[:80])
            print("  dm type:", type(r.disposition_match))
    await engine.dispose()


asyncio.run(main())
