from pydantic import BaseModel, Field


class KnowledgebaseProfile(BaseModel):
    name: str = Field(description="The name of the knowledgebase.")

    description: str = Field(description="The description of the knowledgebase.")

    tags: list[str] = Field(
        description="Some tags of the knowledgebase. It represents the category of the knowledgebase. About 3-5 tags should be provided."
    )

    keywords: list[str] = Field(
        description="Recommanded query keywords of the knowledgebase. About 3-5 keywords should be provided."
    )
