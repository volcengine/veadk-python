
from veadk import Agent, Runner
from veadk.tools.builtin_tools.video_generate import video_generate
from veadk.tools.builtin_tools.image_generate import image_generate
from veadk.memory.short_term_memory import ShortTermMemory

app_name = "veadk_app"
user_id = "veadk_user"
session_id = "veadk_session"

agent = Agent( 
    name="quick_video_create_agent",
    description=("You are an expert in creating images and video"),
    instruction="""You can create images and using the images to generate video, 
                 first you using the image_generate tool to create an image as the first_frame and next create the last_frame, 
                 then you using the generated first_frame and last_frame to invoke video_generate tool to create a video.
                 After the video is created, you need to return the full absolute path of the video avoid the user cannot find the video
                 and give a quick summary of the content of the video.
                """,
    tools=[image_generate, video_generate],
)


short_term_memory = ShortTermMemory()  

runner = Runner(
    agent=agent, short_term_memory=short_term_memory, app_name=app_name, user_id=user_id
)

async def main():
    response = await runner.run(
        messages="首先生成一只小狗图片，然后生成一个小狗飞上天抓老鼠的图片，最终合成一个视频", session_id=session_id
    )
    print(response)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())