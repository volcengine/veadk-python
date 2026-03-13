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

"""
Example: Training Vanna with VikingDB and using it with VeADK Agent

This example demonstrates:
1. Training a Vanna model using VikingDB as the backend (Vanna 1.0 style)
2. Using the trained model with VeADK Agent and VannaToolSet
"""

from veadk import Agent, Runner
from veadk.tools.vanna_tools.vanna_toolset import VannaToolSet
from veadk.tools.vanna_tools.vanna_trainer import VannaTrainer


# Step 1: Train the Vanna model with VikingDB
print("=" * 80)
print("STEP 1: Training Vanna with VikingDB")
print("=" * 80)

# Initialize the trainer with VikingDB backend
trainer = VannaTrainer(
    collection_prefix="chinook_vanna",  # Unique name for your project
    region="cn-beijing",
)

# Train with DDL (table schemas)
print("\nTraining with DDL...")
trainer.train(
    ddl="""
CREATE TABLE [Album]
(
    [AlbumId] INTEGER  NOT NULL,
    [Title] NVARCHAR(160)  NOT NULL,
    [ArtistId] INTEGER  NOT NULL,
    CONSTRAINT [PK_Album] PRIMARY KEY  ([AlbumId]),
    FOREIGN KEY ([ArtistId]) REFERENCES [Artist] ([ArtistId])
)
"""
)

trainer.train(
    ddl="""
CREATE TABLE [Artist]
(
    [ArtistId] INTEGER  NOT NULL,
    [Name] NVARCHAR(120),
    CONSTRAINT [PK_Artist] PRIMARY KEY  ([ArtistId])
)
"""
)

trainer.train(
    ddl="""
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
    CONSTRAINT [PK_Track] PRIMARY KEY  ([TrackId])
)
"""
)

# Train with documentation
print("\nTraining with documentation...")
trainer.train(
    documentation="The Chinook database represents a digital media store, including tables for artists, albums, media tracks, invoices and customers."
)

trainer.train(
    documentation="The Album table contains album information and has a foreign key relationship with Artist table through ArtistId."
)

# Train with question-SQL pairs
print("\nTraining with question-SQL pairs...")
trainer.train(
    question="Get all the tracks in the album 'Balls to the Wall'",
    sql="SELECT * FROM Track WHERE AlbumId = (SELECT AlbumId FROM Album WHERE Title = 'Balls to the Wall')",
)

trainer.train(
    question="How many tracks are there in each album?",
    sql="SELECT a.Title, COUNT(t.TrackId) as TrackCount FROM Album a JOIN Track t ON a.AlbumId = t.AlbumId GROUP BY a.AlbumId",
)

trainer.train(
    question="List all artists with their album count",
    sql="SELECT ar.Name, COUNT(al.AlbumId) as AlbumCount FROM Artist ar LEFT JOIN Album al ON ar.ArtistId = al.ArtistId GROUP BY ar.ArtistId",
)

# Bulk training example
print("\nBulk training...")
trainer.train_bulk(
    question_sql_pairs=[
        (
            "What are the top 5 longest tracks?",
            "SELECT Name, Milliseconds FROM Track ORDER BY Milliseconds DESC LIMIT 5",
        ),
        ("How many artists are there?", "SELECT COUNT(*) as TotalArtists FROM Artist"),
    ]
)

print("\n✅ Training completed! Data stored in VikingDB.")


# Step 2: Use the trained model with VeADK Agent
print("\n" + "=" * 80)
print("STEP 2: Using trained model with VeADK Agent")
print("=" * 80)

# Get the trained agent memory
agent_memory = trainer.get_agent_memory()

# Create VannaToolSet with the trained memory
vanna_toolset = VannaToolSet(
    connection_string="sqlite:///tmp/Chinook.sqlite",
    file_storage="/tmp/vanna_files",
    agent_memory=agent_memory,  # Use the trained VikingDB memory
)

# Define the VeADK Agent with the trained toolset
agent = Agent(
    name="vanna_sql_agent_with_vikingdb",
    description="An intelligent agent that can query databases using trained VikingDB knowledge.",
    instruction="""
    You are a helpful assistant that can answer questions about data in the Chinook database.
    You have been trained with:
    - Database schemas (DDL)
    - Documentation about the database
    - Example question-SQL pairs
    
    When answering questions:
    1. First search for similar questions using search_saved_correct_tool_uses
    2. Use the retrieved DDL and documentation to understand the schema
    3. Generate and execute appropriate SQL queries
    4. Present results in a clear format
    """,
    tools=[vanna_toolset],
    model_extra_config={"extra_body": {"thinking": {"type": "disabled"}}},
)

print("\n✅ Agent initialized with trained VikingDB knowledge.")
print("\nYou can now run the agent with queries like:")
print("  - How many albums are there in total?")
print("  - Show me the top 10 longest tracks")
print("  - Which artist has the most albums?")


# Step 3: Test the agent
print("\n" + "=" * 80)
print("STEP 3: Testing the agent")
print("=" * 80)


async def test_agent():
    """Test the agent with a sample query."""

    # Create runner
    runner = Runner(
        agent=agent,
    )

    # Test query
    test_question = "How many albums are there in total?"
    print(f"\nQuery: {test_question}")
    print("-" * 80)

    response = await runner.run(
        new_message=test_question,
    )

    print(f"\nResponse: {response}")
    print("-" * 80)


# Run the test
if __name__ == "__main__":
    import asyncio

    print("\nRunning test query...")
    asyncio.run(test_agent())

    print("\n" + "=" * 80)
    print("✅ Example completed successfully!")
    print("=" * 80)
    print("\nNext steps:")
    print("1. The trained knowledge is stored in VikingDB")
    print("2. You can add more training data anytime using trainer.train()")
    print(
        "3. The agent will automatically use the trained knowledge to answer questions"
    )
    print(
        "4. Similar questions will be retrieved from VikingDB for better SQL generation"
    )
