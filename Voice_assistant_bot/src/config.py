from pydantic_settings import BaseSettings

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from openai import OpenAI

from concurrent.futures import ThreadPoolExecutor

class Settings(BaseSettings):
    openai_api_key: str
    telegram_bot_token: str
    database_url: str
    amplitude_api_key: str

    class Config:
        env_file = 'D:\Programming\Python\GPT\Voice_AI_bot_on_Aiogram\Voice_assistant_bot_2\.env'

set = Settings()

bot_tg = Bot(token=set.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

client = OpenAI(api_key=set.openai_api_key)

executor = ThreadPoolExecutor(max_workers=5)

assistant = client.beta.assistants.create(
    name="Professional interlocutor",
    instructions="You are a professional interlocutor. You need to answer questions, ask your own and maintain dialogue as much as possible.",
    model="gpt-4o",
    tools=[
        {"type": "file_search"},
        {
            "type": "function",
            "function": {
                "name": "save_value",
                "description": "Define and gather user opinions and key values",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "opinions": {
                            "type": "string",
                            "description": "Opinions"
                        },
                        "values": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "Values important"
                        }
                    },
                    "required": ["opinions", "values"]
                }
            }
        }
    ]
)
           
thread = client.beta.threads.create()

# Create a vector store caled "Financial Statements"
vector_store = client.beta.vector_stores.create(name="Financial Statements")
    
# Ready the files for upload to OpenAI
file_paths = ["C:\\Users\\thatn\\Desktop\\At_Latoken.docx", "C:\\Users\\thatn\\Desktop\\Anxiety.docx"]
file_streams = [open(path, "rb") for path in file_paths]
    
# Use the upload and poll SDK helper to upload the files, add them to the vector store,
# and poll the status of the file batch for completion.
file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
    vector_store_id=vector_store.id, files=file_streams
)
    
# You can print the status and the file counts of the batch to see the result of this operation.
# print(file_batch.status)
# print(file_batch.file_counts)

assistant = client.beta.assistants.update(
    assistant_id=assistant.id,
    tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
)

# Upload the user provided file to OpenAI
message_file_0 = client.files.create(
    file = open("C:\\Users\\thatn\\Desktop\\At_Latoken.docx", "rb"), purpose="assistants"
)

message_file_1 = client.files.create(
    file = open("C:\\Users\\thatn\\Desktop\\Anxiety.docx", "rb"), purpose="assistants"
)
    
# Create a thread and attach the file to the message
thread =  client.beta.threads.create(
    messages=[
        {
        "role": "user",
        "content": "Что такое тревожность?",
        # Attach the new file to the message.
        "attachments": [
            { "file_id": message_file_0.id, "tools": [{"type": "file_search"}] },
            { "file_id": message_file_1.id, "tools": [{"type": "file_search"}] }
        ],
        }
    ]
)
    
# The thread now has a vector store with that file in its tool resources.
# print(thread.tool_resources.file_search)

# Use the create and poll SDK helper to create a run and poll the status of
# the run until it's in a terminal state.

run = client.beta.threads.runs.create_and_poll(
    thread_id=thread.id, assistant_id=assistant.id
)

messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))

message_content = messages[0].content[0].text
annotations = message_content.annotations
citations = []
for index, annotation in enumerate(annotations):
    message_content.value = message_content.value.replace(annotation.text, f"[{index}]")
    if file_citation := getattr(annotation, "file_citation", None):
        cited_file = client.files.retrieve(file_citation.file_id)
        citations.append(f"[{index}] {cited_file.filename}")




