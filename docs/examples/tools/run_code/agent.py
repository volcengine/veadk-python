
from veadk import Agent, Runner
from veadk.tools.builtin_tools.web_search import web_search
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools.builtin_tools.run_code import run_code

app_name = "veadk_app"
user_id = "veadk_user"
session_id = "veadk_session"

agent: Agent = Agent(
    name="data_analysis_agent",
    description="A data analysis for stock marketing",
    instruction="""
        你是一个资深软件工程师，在沙箱里执行生产的代码， 避免每次安装检查, 
        可以使用python lib akshare 下载相关的股票数据。可以通过web_search工具搜索相关公司的经营数据。如果缺失了依赖库, 
        通过python代码为沙箱安装缺失的依赖库。""",
    tools=[run_code, web_search],
)


short_term_memory = ShortTermMemory()  

runner = Runner(
    agent=agent, short_term_memory=short_term_memory, app_name=app_name, user_id=user_id
)

async def main():
    response = await runner.run(
        messages="阳光电源？", session_id=session_id
    )
    print(response)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())