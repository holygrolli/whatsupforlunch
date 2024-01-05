import openai, sys
from datetime import datetime, timedelta
import base64
import json
import mimetypes

class DefaultMealChat:
    def __init__(self, 
                    systemPrompt=None, 
                    systemPromptFile="chatgpt_systemprompt.txt", 
                    userMessage=None, 
                    userMessageFile="chatgpt_user.txt",
                    userMessagePrefix="",
                    userImageFile="image_input",
                    dateOverride=None,
                    jsonSchema=None,
                    max_tokens=1000):
        # if dateOverride is set, use it
        if dateOverride is not None:
            today = datetime.strptime(dateOverride, '%Y-%m-%d')
        else:
            today = datetime.today()
        weekStart = today - timedelta(days=today.weekday())
        # if on weekend assume we are running for next week
        if today.weekday()>4:
            weekStart = weekStart + timedelta(days=7)
        self.weekStart = weekStart

        self.userImageFile = userImageFile
        self.userMessagePrefix = userMessagePrefix.format(MC_TODAY=self.weekStart.strftime("%Y-%m-%d"), MC_WEEKSTART=self.weekStart.strftime("%G-W%V"))
        self.max_tokens = max_tokens
        if systemPrompt is None:
            file = open(systemPromptFile, "r")
            self.systemPrompt = file.read()
            file.close()
        else:
            self.systemPrompt = systemPrompt
        self.systemPrompt = self.systemPrompt.format(MC_JSON_SCHEMA=jsonSchema, MC_TODAY=self.weekStart.strftime("%Y-%m-%d"), MC_WEEKSTART=self.weekStart.strftime("%G-W%V"))
        if userMessage is None:
            file = open(userMessageFile, "r")
            self.userMessage = file.read()
            file.close()
        else:
            self.userMessage = userMessage

    def encode_image_and_return_string(self, image_path):
        with open(image_path, "rb") as image_file:
            # Determine the mime type based on the file extension
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:{self.detect_mime_type(image_path)};base64,{base64_image}"

    def detect_mime_type(self, image_path):
        mime_type, _ = mimetypes.guess_type(image_path)
        print(f"mime_type of input: {mime_type}")
        return mime_type

    def extract_json_content(self, text):
        start_index = text.find("{")
        end_index = text.rfind("}")
        json_content = text[start_index:end_index+1]
        return json_content

    def writeToFile(self, chat_completion):
        print(chat_completion.usage)
        out = open("usage.json", "w")
        out.write(str(chat_completion.usage))
        out.close()
        # print the chat completion for debugging
        print(chat_completion.choices[0].message.content)
        out = open("chatgpt.json", "w")
        out.write(self.extract_json_content(chat_completion.choices[0].message.content))
        out.close()

    def processImageAndWriteToFile(self):
        print("Using the prompt: " + self.systemPrompt)
        gpt_messages=[
            {"role": "system", "content": self.systemPrompt}]
        gpt_messages.append({"role": "user", "content": [
            {
                "type": "text",
                "text": self.userMessagePrefix + self.userMessage
            },
            {
                "type": "image_url",
                "image_url": self.encode_image_and_return_string(self.userImageFile)
            }
        ]})
        
        #print("gpt_messages: " + str(gpt_messages))
        print(f"sending additional user msg: {self.userMessagePrefix + self.userMessage}")
        chat_completion = openai.ChatCompletion.create(model="gpt-4-vision-preview",
                                                        messages=gpt_messages,
                                                        max_tokens=self.max_tokens)#,
                                                        #response_format={ "type":"json_object" })
        self.writeToFile(chat_completion)

    def processAndWriteToFile(self):
        # print the system prompt for debugging
        print("Using the prompt: " + self.systemPrompt)
        gpt_messages=[
            {"role": "system", "content": self.systemPrompt},
            {"role": "user", "content": self.userMessagePrefix + self.userMessage}]
        print("gpt_messages: " + str(gpt_messages))
        chat_completion = openai.ChatCompletion.create(model="gpt-3.5-turbo-1106",
                                                        messages=gpt_messages,
                                                        response_format={ "type":"json_object" },
                                                        max_tokens=self.max_tokens)
        self.writeToFile(chat_completion)
