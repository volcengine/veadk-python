import os
import httpx
import pandas as pd
import io
from typing import Optional, Dict, Any
import requests

from vanna.integrations.sqlite import SqliteRunner
from vanna.tools.file_system import (
    LocalFileSystem,
    WriteFileTool,
    ReadFileTool,
    EditFileTool,
    ListFilesTool,
    SearchFilesTool,
)
from vanna.tools import RunSqlTool, VisualizeDataTool
from vanna.tools.python import RunPythonFileTool, PipInstallTool
from vanna.tools.agent_memory import (
    SaveQuestionToolArgsTool,
    SearchSavedCorrectToolUsesTool,
    SaveTextMemoryTool,
)
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna.core.tool import ToolContext
from vanna.core.user import User


# Setup SQLite
def setup_sqlite():
    # Use the generated B2B sample data
    # Note: In VeFaaS, only /tmp is writable, so we might need to copy it there if we want to modify it.
    # But for read-only access or local dev, we can point to the sample_data directory.

    # Try to find the sample data relative to this file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up one level to src, then to sample_data
    sample_data_path = os.path.join(
        os.path.dirname(current_dir), "sample_data", "b2b_crm.sqlite"
    )

    if os.path.exists(sample_data_path):
        return sample_data_path

    # Fallback to Chinook if B2B data not found (or for compatibility)
    db_path = "/tmp/Chinook.sqlite"
    if not os.path.exists(db_path):
        print("Downloading Chinook.sqlite...")
        url = "https://vanna.ai/Chinook.sqlite"
        try:
            with open(db_path, "wb") as f:
                with httpx.stream("GET", url) as response:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
        except Exception as e:
            print(f"Error downloading database: {e}")
    return db_path


# Initialize Resources
db_path = setup_sqlite()
# Use /tmp for file storage as it's the only writable directory in VeFaaS
file_system = LocalFileSystem(working_directory="/tmp/data_storage")
if not os.path.exists("/tmp/data_storage"):
    os.makedirs("/tmp/data_storage", exist_ok=True)

sqlite_runner = SqliteRunner(database_path=db_path)
agent_memory = DemoAgentMemory(max_items=1000)

# Initialize Vanna Tools
sql_tool = RunSqlTool(sql_runner=sqlite_runner, file_system=file_system)
viz_tool = VisualizeDataTool(file_system=file_system)
run_python_tool = RunPythonFileTool(file_system=file_system)
pip_install_tool = PipInstallTool(file_system=file_system)

# File System Tools
write_file_tool = WriteFileTool(file_system=file_system)
read_file_tool = ReadFileTool(file_system=file_system)
edit_file_tool = EditFileTool(file_system=file_system)
list_files_tool = ListFilesTool(file_system=file_system)
search_files_tool = SearchFilesTool(file_system=file_system)

save_mem_tool = SaveQuestionToolArgsTool()
search_mem_tool = SearchSavedCorrectToolUsesTool()
save_text_mem_tool = SaveTextMemoryTool()

# Create a mock context for tool execution
# In a real application, this should be created per-request with the actual user
mock_user = User(
    id="veadk-user", email="user@example.com", group_memberships=["admin", "user"]
)
mock_context = ToolContext(
    user=mock_user,
    conversation_id="default",
    request_id="default",
    agent_memory=agent_memory,
)

# Wrapper Functions for Veadk Agent


async def run_sql(sql: str) -> str:
    """
    Execute a SQL query against the Chinook database.

    Args:
        sql: The SQL query to execute.
    """
    args_model = sql_tool.get_args_schema()(sql=sql)
    result = await sql_tool.execute(mock_context, args_model)
    return str(result.result_for_llm)


async def visualize_data(filename: str, title: str = None) -> str:
    """
    Visualize data from a CSV file.

    Args:
        filename: The name of the CSV file to visualize.
        title: Optional title for the chart.
    """
    # Check if the file is likely a CSV file
    if not filename.lower().endswith(".csv"):
        return (
            f"Error: visualize_data only supports CSV files. You provided: {filename}"
        )

    args_model = viz_tool.get_args_schema()(filename=filename, title=title)
    result = await viz_tool.execute(mock_context, args_model)
    return str(result.result_for_llm)


async def run_python_file(filename: str) -> str:
    """
    Execute a Python file.

    Args:
        filename: The name of the Python file to execute.
    """
    # Check if the file is likely a Python file
    if not filename.lower().endswith(".py"):
        return f"Error: run_python_file only supports Python files. You provided: {filename}"

    args_model = run_python_tool.get_args_schema()(filename=filename)
    result = await run_python_tool.execute(mock_context, args_model)
    return str(result.result_for_llm)


async def pip_install(packages: list[str]) -> str:
    """
    Install Python packages using pip.

    Args:
        packages: List of package names to install.
    """
    args_model = pip_install_tool.get_args_schema()(packages=packages)
    result = await pip_install_tool.execute(mock_context, args_model)
    return str(result.result_for_llm)


async def read_file(filename: str, start_line: int = 1, end_line: int = -1) -> str:
    """
    Read the content of a file.

    Args:
        filename: The name of the file to read.
        start_line: The line number to start reading from (1-based).
        end_line: The line number to stop reading at (inclusive). -1 for end of file.
    """
    args_model = read_file_tool.get_args_schema()(
        filename=filename, start_line=start_line, end_line=end_line
    )
    result = await read_file_tool.execute(mock_context, args_model)
    return str(result.result_for_llm)


async def edit_file(filename: str, edits: list[dict[str, Any]]) -> str:
    """
    Edit a file by replacing lines.

    Args:
        filename: The name of the file to edit.
        edits: A list of edits to apply. Each edit is a dictionary with:
            - start_line: The line number to start replacing (1-based).
            - end_line: The line number to stop replacing (inclusive).
            - new_content: The new content to insert.
    """
    # Convert dicts to EditFileTool.Edit objects if necessary, but Pydantic should handle dicts
    args_model = edit_file_tool.get_args_schema()(filename=filename, edits=edits)
    result = await edit_file_tool.execute(mock_context, args_model)
    return str(result.result_for_llm)


async def list_files(path: str = ".") -> str:
    """
    List files in a directory.

    Args:
        path: The directory path to list. Defaults to current directory.
    """
    args_model = list_files_tool.get_args_schema()(path=path)
    result = await list_files_tool.execute(mock_context, args_model)
    return str(result.result_for_llm)


async def search_files(query: str, path: str = ".") -> str:
    """
    Search for files matching a query.

    Args:
        query: The search query (regex or glob pattern).
        path: The directory path to search in. Defaults to current directory.
    """
    args_model = search_files_tool.get_args_schema()(query=query, path=path)
    result = await search_files_tool.execute(mock_context, args_model)
    return str(result.result_for_llm)


async def save_correctanswer_memory(
    question: str, tool_name: str, args: Dict[str, Any]
) -> str:
    """
    Save a successful question-tool-argument combination for future reference.

    Args:
        question: The original question that was asked.
        tool_name: The name of the tool that was used successfully.
        args: The arguments that were passed to the tool.
    """
    # Temporarily disabled due to infinite loop issues
    return "Memory saved successfully (Simulated)"


async def search_similar_tools(question: str, limit: int = 10) -> str:
    """
    Search for similar tool usage patterns based on a question.

    Args:
        question: The question to find similar tool usage patterns for.
        limit: Maximum number of results to return.
    """
    args_model = search_mem_tool.get_args_schema()(question=question, limit=limit)
    result = await search_mem_tool.execute(mock_context, args_model)
    # Return the result (whether success or error message)
    return str(result.result_for_llm)


async def save_text_memory(text: str, tags: list[str] = None) -> str:
    """
    Save arbitrary text to memory for future retrieval.

    Args:
        text: The text content to save.
        tags: Optional list of tags to categorize the memory.
    """
    # Note: SaveTextMemoryParams uses 'content' field, but we expose it as 'text' to the LLM for clarity.
    # We map 'text' to 'content' here. 'tags' are not currently supported by SaveTextMemoryParams in this version of Vanna.
    args_model = save_text_mem_tool.get_args_schema()(content=text)
    result = await save_text_mem_tool.execute(mock_context, args_model)
    return str(result.result_for_llm)


async def generate_document(filename: str, content: str) -> str:
    """
    Generate a document (save content to a file).

    Args:
        filename: The name of the file to save (e.g., 'report.md', 'summary.txt').
        content: The text content to write to the file.
    """
    args_model = write_file_tool.get_args_schema()(
        filename=filename, content=content, overwrite=True
    )
    result = await write_file_tool.execute(mock_context, args_model)
    return str(result.result_for_llm)


async def summarize_data(filename: str) -> str:
    """
    Generate a statistical summary of data from a CSV file.

    Args:
        filename: The name of the CSV file to summarize.
    """
    try:
        # Read the file content
        content = await file_system.read_file(filename, mock_context)

        # Parse into DataFrame
        df = pd.read_csv(io.StringIO(content))

        # Generate summary stats
        description = df.describe().to_markdown()
        head = df.head().to_markdown()
        info = f"Rows: {len(df)}, Columns: {len(df.columns)}\nColumn Names: {', '.join(df.columns)}"

        summary = f"**Data Summary for {filename}**\n\n**Info:**\n{info}\n\n**First 5 Rows:**\n{head}\n\n**Statistical Description:**\n{description}"
        return summary
    except Exception as e:
        return f"Failed to summarize data: {str(e)}"


# def query_with_dsl(dsl_json: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
#     """
#     使用DSL JSON查询数据的函数

#     Args:
#         dsl_json: 完整的DSL查询JSON对象
#         timeout: 请求超时时间（秒）

#     Returns:
#         格式化后的查询结果字典

#     Example:
#         dsl = {
#             "Operator": "liujiawei.boom@bytedance.com",
#             "Tenant": "c360",
#             "Table": "large_model_usage",
#             "Select": "account_number, request_date, token_amount",
#             "GroupBy": "account_number, request_date",
#             "Where": "request_date >= '2025-11-24' and account_number != 'ACC-0000872346'",
#             "OrderBy": "",
#             "Limit": 100
#         }
#         result = query_with_dsl(dsl)
#     """
#     # API端点
#     host = "bytedance"
#     url = f"http://eps-agent.{host}.net/search_metadata/query?Action=Query"

#     # 请求头
#     headers = {
#         "Content-Type": "application/json"
#     }

#     try:
#         # 发送POST请求
#         response = requests.post(url, headers=headers, json=dsl_json, timeout=timeout)

#         # 检查响应状态
#         response.raise_for_status()

#         # 解析JSON响应
#         result = response.json()

#         # 格式化输出
#         formatted_result = {
#             "ResponseMetadata": {
#                 "RequestId": result.get("ResponseMetadata", {}).get("RequestId", "")
#             },
#             "Result": []
#         }

#         # 提取结果数据
#         if "Result" in result:
#             for item in result["Result"]:
#                 formatted_item = {
#                     "account_id": item.get("account_id", ""),
#                     "account_number": item.get("account_number", ""),
#                     "request_date": item.get("request_date", ""),
#                     "token_amount": item.get("token_amount", 0)
#                 }
#                 formatted_result["Result"].append(formatted_item)

#         return formatted_result

#     except requests.exceptions.RequestException as e:
#         raise Exception(f"请求错误: {e}")
#     except json.JSONDecodeError as e:
#         raise Exception(f"JSON解析错误: {e}")
#     except Exception as e:
#         raise Exception(f"未知错误: {e}")


def query_with_dsl(
    operator: str,
    tenant: str,
    table: str,
    select: str,
    group_by: Optional[str] = None,
    where: Optional[str] = None,
    order_by: Optional[str] = None,
    limit: Optional[int] = 100,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    查询数据的函数

    Args:
        operator: 操作者标识，通常为企业邮箱，用于审计和权限校验
        tenant: 租户标识，需与元数据查询时保持一致
        table: 需要查询的数据表名
        select: 需要查询的字段列表，多个字段间用英文逗号分隔
        group_by: 分组字段列表，多个字段间用英文逗号分隔
        where: 筛选条件，采用 SQL-like 语法
        order_by: 排序条件，格式为 "字段名 ASC/DESC"
        limit: 返回记录的最大数量，默认为 100
        timeout: 请求超时时间（秒）

    Returns:
        查询结果字典

    Example:
        result = query_data(
            operator="liujiawei.boom@bytedance.com",
            tenant="c360",
            table="large_model_usage",
            select="account_number, request_date, token_amount",
            group_by="account_number, request_date",
            where="request_date >= '2025-11-24' and account_number != 'ACC-0000872346'",
            order_by="request_date DESC",
            limit=100
        )
    """
    # API端点
    host = "bytedance"
    url = f"http://eps-agent.{host}.net/search_metadata/query?Action=Query"

    # 构建请求体
    payload = {
        "Operator": operator,
        "Tenant": tenant,
        "Table": table,
        "Select": select,
    }

    # 添加可选参数
    if group_by:
        payload["GroupBy"] = group_by
    if where:
        payload["Where"] = where
    if order_by:
        payload["OrderBy"] = order_by
    if limit is not None:
        payload["Limit"] = limit

    # 请求头
    headers = {"Content-Type": "application/json"}

    try:
        # 发送POST请求
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)

        # 解析JSON响应
        result = response.json()

        # 检查响应状态
        response.raise_for_status()

        return result

    except Exception as e:
        return f"错误: {e}, 返回内容: {result}"


def recall_metadata(tenant: str, query: str, timeout: int = 30) -> Dict[str, Any]:
    """
    调用元数据查询接口的函数

    Args:
        tenant: 租户名称
        query: 查询文本
        timeout: 请求超时时间（秒）

    Returns:
        查询结果字典

    Example:
        result = recall_metadata(
            tenant="c360",
            query="小米的收入是多少？"
        )
    """
    # API端点
    host = "bytedance"
    url = f"http://eps-agent.{host}.net/search_metadata/metadata?Action=RecallMetadata"

    # 请求头
    headers = {"Content-Type": "application/json"}

    # 请求体
    payload = {"Tenant": tenant, "Query": query}

    try:
        # 发送POST请求
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)

        result = response.json()

        # 检查响应状态
        response.raise_for_status()

        # 解析JSON响应
        return result

    except requests.exceptions.RequestException as e:
        return f"错误: {e}, 返回内容: {result}"
