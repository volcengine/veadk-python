# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from veadk import Agent, Runner
from veadk.tools.vanna_tools.vanna_toolset import VannaToolSet
from google.adk.sessions import InMemorySessionService


# Create a session with user groups for access control
async def create_session(user_groups: list = ["user"]):
    session_service = InMemorySessionService()
    example_session = await session_service.create_session(
        app_name="example_app",
        user_id="example_user",
        state={"user_groups": user_groups},
    )
    return session_service, example_session


vanna_toolset = VannaToolSet(
    connection_string="sqlite:///tmp/Chinook.sqlite", file_storage="/tmp/vanna_files"
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
    tools=[vanna_toolset],
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

    print("=== Example 1: Regular User ===")
    user_input = "What are the top 5 selling albums?"
    response = asyncio.run(main(user_input, user_groups=["user"]))
    print(response)
