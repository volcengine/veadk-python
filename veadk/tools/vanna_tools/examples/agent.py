import os
from veadk import Agent, Runner

# Import Vanna dependencies for initialization
from vanna.integrations.sqlite import SqliteRunner
from vanna.tools import LocalFileSystem
from vanna.integrations.local.agent_memory import DemoAgentMemory
import httpx

# Import the refactored class-based tools
from veadk.tools.vanna_tools.run_sql import RunSqlTool
from veadk.tools.vanna_tools.visualize_data import VisualizeDataTool
from veadk.tools.vanna_tools.file_system import WriteFileTool
from veadk.tools.vanna_tools.agent_memory import (
    SaveQuestionToolArgsTool,
    SearchSavedCorrectToolUsesTool,
)
from veadk.tools.vanna_tools.summarize_data import SummarizeDataTool

from google.adk.sessions import InMemorySessionService


# Setup SQLite database
def setup_sqlite():
    """Download and setup the Chinook SQLite database."""
    db_path = "/tmp/Chinook.sqlite"
    if not os.path.exists(db_path):
        print("Downloading Chinook.sqlite...")
        url = "https://vanna.ai/Chinook.sqlite"
        try:
            with open(db_path, "wb") as f:
                with httpx.stream("GET", url) as response:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
            print("Database downloaded successfully!")
        except Exception as e:
            print(f"Error downloading database: {e}")
    return db_path


async def create_session(user_groups: list = ["user"]):
    session_service = InMemorySessionService()
    example_session = await session_service.create_session(
        app_name="example_app",
        user_id="example_user",
        state={"user_groups": user_groups},
    )
    return session_service, example_session


# Initialize user-customizable resources
db_path = setup_sqlite()

# 1. SQL Runner - can be SqliteRunner, PostgresRunner, MySQLRunner, etc.
sqlite_runner = SqliteRunner(database_path=db_path)

# 2. File System - customize working directory as needed
file_system = LocalFileSystem(working_directory="/tmp/data_storage")
if not os.path.exists("/tmp/data_storage"):
    os.makedirs("/tmp/data_storage", exist_ok=True)

# 3. Agent Memory - customize memory implementation and capacity
agent_memory = DemoAgentMemory(max_items=1000)

# Initialize tools with user-defined components and access control
# Tool names now match Vanna's original names for compatibility
run_sql_tool = RunSqlTool(
    sql_runner=sqlite_runner,
    file_system=file_system,
    agent_memory=agent_memory,
    access_groups=["admin", "user"],  # Both admin and user can use
)

visualize_data_tool = VisualizeDataTool(
    file_system=file_system,
    agent_memory=agent_memory,
    access_groups=["admin", "user"],
)

write_file_tool = WriteFileTool(
    file_system=file_system,
    agent_memory=agent_memory,
    access_groups=["admin", "user"],
)

# Memory tools: save only for admin, search for all users
save_tool = SaveQuestionToolArgsTool(
    agent_memory=agent_memory,
    access_groups=["admin"],  # Only admin can save
)

search_tool = SearchSavedCorrectToolUsesTool(
    agent_memory=agent_memory,
    access_groups=["admin", "user"],  # All users can search
)

summarize_data_tool = SummarizeDataTool(
    file_system=file_system,
    agent_memory=agent_memory,
    access_groups=["admin", "user"],
)

# Define the Veadk Agent with class-based tools
agent: Agent = Agent(
    name="vanna_sql_agent",
    description="An intelligent agent that can query databases, visualize data, and generate reports.",
    instruction="""
    You are a helpful assistant that can answer questions about data in the Chinook database.
    You can execute SQL queries, visualize the results, save/search useful tool usage patterns, and generate documents.

    Here is the schema of the Chinook database:
    ```sql
    CREATE TABLE [Album]
    (
        [AlbumId] INTEGER  NOT NULL,
        [Title] NVARCHAR(160)  NOT NULL,
        [ArtistId] INTEGER  NOT NULL,
        CONSTRAINT [PK_Album] PRIMARY KEY  ([AlbumId]),
        FOREIGN KEY ([ArtistId]) REFERENCES [Artist] ([ArtistId]) 
                    ON DELETE NO ACTION ON UPDATE NO ACTION
    );
    CREATE TABLE [Artist]
    (
        [ArtistId] INTEGER  NOT NULL,
        [Name] NVARCHAR(120),
        CONSTRAINT [PK_Artist] PRIMARY KEY  ([ArtistId])
    );
    CREATE TABLE [Customer]
    (
        [CustomerId] INTEGER  NOT NULL,
        [FirstName] NVARCHAR(40)  NOT NULL,
        [LastName] NVARCHAR(20)  NOT NULL,
        [Company] NVARCHAR(80),
        [Address] NVARCHAR(70),
        [City] NVARCHAR(40),
        [State] NVARCHAR(40),
        [Country] NVARCHAR(40),
        [PostalCode] NVARCHAR(10),
        [Phone] NVARCHAR(24),
        [Fax] NVARCHAR(24),
        [Email] NVARCHAR(60)  NOT NULL,
        [SupportRepId] INTEGER,
        CONSTRAINT [PK_Customer] PRIMARY KEY  ([CustomerId]),
        FOREIGN KEY ([SupportRepId]) REFERENCES [Employee] ([EmployeeId]) 
                    ON DELETE NO ACTION ON UPDATE NO ACTION
    );
    CREATE TABLE [Employee]
    (
        [EmployeeId] INTEGER  NOT NULL,
        [LastName] NVARCHAR(20)  NOT NULL,
        [FirstName] NVARCHAR(20)  NOT NULL,
        [Title] NVARCHAR(30),
        [ReportsTo] INTEGER,
        [BirthDate] DATETIME,
        [HireDate] DATETIME,
        [Address] NVARCHAR(70),
        [City] NVARCHAR(40),
        [State] NVARCHAR(40),
        [Country] NVARCHAR(40),
        [PostalCode] NVARCHAR(10),
        [Phone] NVARCHAR(24),
        [Fax] NVARCHAR(24),
        [Email] NVARCHAR(60),
        CONSTRAINT [PK_Employee] PRIMARY KEY  ([EmployeeId]),
        FOREIGN KEY ([ReportsTo]) REFERENCES [Employee] ([EmployeeId]) 
                    ON DELETE NO ACTION ON UPDATE NO ACTION
    );
    CREATE TABLE [Genre]
    (
        [GenreId] INTEGER  NOT NULL,
        [Name] NVARCHAR(120),
        CONSTRAINT [PK_Genre] PRIMARY KEY  ([GenreId])
    );
    CREATE TABLE [Invoice]
    (
        [InvoiceId] INTEGER  NOT NULL,
        [CustomerId] INTEGER  NOT NULL,
        [InvoiceDate] DATETIME  NOT NULL,
        [BillingAddress] NVARCHAR(70),
        [BillingCity] NVARCHAR(40),
        [BillingState] NVARCHAR(40),
        [BillingCountry] NVARCHAR(40),
        [BillingPostalCode] NVARCHAR(10),
        [Total] NUMERIC(10,2)  NOT NULL,
        CONSTRAINT [PK_Invoice] PRIMARY KEY  ([InvoiceId]),
        FOREIGN KEY ([CustomerId]) REFERENCES [Customer] ([CustomerId]) 
                    ON DELETE NO ACTION ON UPDATE NO ACTION
    );
    CREATE TABLE [InvoiceLine]
    (
        [InvoiceLineId] INTEGER  NOT NULL,
        [InvoiceId] INTEGER  NOT NULL,
        [TrackId] INTEGER  NOT NULL,
        [UnitPrice] NUMERIC(10,2)  NOT NULL,
        [Quantity] INTEGER  NOT NULL,
        CONSTRAINT [PK_InvoiceLine] PRIMARY KEY  ([InvoiceLineId]),
        FOREIGN KEY ([InvoiceId]) REFERENCES [Invoice] ([InvoiceId]) 
                    ON DELETE NO ACTION ON UPDATE NO ACTION,
        FOREIGN KEY ([TrackId]) REFERENCES [Track] ([TrackId]) 
                    ON DELETE NO ACTION ON UPDATE NO ACTION
    );
    CREATE TABLE [MediaType]
    (
        [MediaTypeId] INTEGER  NOT NULL,
        [Name] NVARCHAR(120),
        CONSTRAINT [PK_MediaType] PRIMARY KEY  ([MediaTypeId])
    );
    CREATE TABLE [Playlist]
    (
        [PlaylistId] INTEGER  NOT NULL,
        [Name] NVARCHAR(120),
        CONSTRAINT [PK_Playlist] PRIMARY KEY  ([PlaylistId])
    );
    CREATE TABLE [PlaylistTrack]
    (
        [PlaylistId] INTEGER  NOT NULL,
        [TrackId] INTEGER  NOT NULL,
        CONSTRAINT [PK_PlaylistTrack] PRIMARY KEY  ([PlaylistId], [TrackId]),
        FOREIGN KEY ([PlaylistId]) REFERENCES [Playlist] ([PlaylistId]) 
                    ON DELETE NO ACTION ON UPDATE NO ACTION,
        FOREIGN KEY ([TrackId]) REFERENCES [Track] ([TrackId]) 
                    ON DELETE NO ACTION ON UPDATE NO ACTION
    );
    CREATE TABLE [Track]
    (
        [TrackId] INTEGER  NOT NULL,
        [Name] NVARCHAR(200)  NOT NULL,
        [AlbumId] INTEGER,
        [MediaTypeId] INTEGER  NOT NULL,
        [GenreId] INTEGER,
        [Composer] NVARCHAR(220),
        [Milliseconds] INTEGER  NOT NULL,
        [Bytes] INTEGER,
        [UnitPrice] NUMERIC(10,2)  NOT NULL,
        CONSTRAINT [PK_Track] PRIMARY KEY  ([TrackId]),
        FOREIGN KEY ([AlbumId]) REFERENCES [Album] ([AlbumId]) 
                    ON DELETE NO ACTION ON UPDATE NO ACTION,
        FOREIGN KEY ([GenreId]) REFERENCES [Genre] ([GenreId]) 
                    ON DELETE NO ACTION ON UPDATE NO ACTION,
        FOREIGN KEY ([MediaTypeId]) REFERENCES [MediaType] ([MediaTypeId]) 
                    ON DELETE NO ACTION ON UPDATE NO ACTION
    );
    ```

    Here are some examples of how to query this database:
    
    Q: Get all the tracks in the album 'Balls to the Wall'.
    A: SELECT * FROM Track WHERE AlbumId = (SELECT AlbumId FROM Album WHERE Title = 'Balls to the Wall')

    Q: Get the total sales for each customer.
    A: SELECT c.FirstName, c.LastName, SUM(i.Total) as TotalSales FROM Customer c JOIN Invoice i ON c.CustomerId = i.CustomerId GROUP BY c.CustomerId

    Q: How many tracks are there in each genre?
    A: SELECT g.Name, COUNT(t.TrackId) as TrackCount FROM Genre g JOIN Track t ON g.GenreId = t.GenreId GROUP BY g.GenreId
    
    Available tools (using Vanna's original names):
    1. `run_sql` - Execute SQL queries
    2. `visualize_data` - Create visualizations from CSV files
    3. `write_file` - Save content to files
    4. `save_question_tool_args` - Save successful tool usage patterns (admin only)
    5. `search_saved_correct_tool_uses` - Search for similar tool usage patterns
    6. `summarize_data` - Generate statistical summaries of CSV files
    """,
    tools=[
        run_sql_tool,
        visualize_data_tool,
        write_file_tool,
        save_tool,
        search_tool,
        summarize_data_tool,
    ],
    model_extra_config={"extra_body": {"thinking": {"type": "disabled"}}},
)


async def main(prompt: str, user_groups: list = None) -> str:
    session_service, example_session = await create_session(
        user_groups
    )  # Default to 'user' group if not specified

    runner = Runner(
        agent=agent,
        app_name=example_session.app_name,
        user_id=example_session.user_id,
        session_service=session_service,
    )

    response = await runner.run(
        messages=prompt,
        session_id=example_session.id,
    )

    return response


if __name__ == "__main__":
    import asyncio

    # print("=== Example 1: Regular User ===")
    # user_input = "What are the top 5 selling albums?"
    # response = asyncio.run(main(user_input, user_groups=['user']))
    # print(response)

    print("\n=== Example 2: Admin User (can save patterns) ===")
    admin_input = "What are the top 5 selling albums?"
    response = asyncio.run(main(admin_input, user_groups=["admin"]))
    print(response)
