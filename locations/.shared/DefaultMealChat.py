from openai import OpenAI
import sys
from datetime import datetime, timedelta
import base64
import json
import mimetypes
import os
from prompt_config import prompt_config

class DefaultMealChat:
    def __init__(self, 
                    userMessage=None, 
                    userMessageFile="chatgpt_user.txt",
                    userMessagePrefix="",
                    userImageFile="image_input",
                    dateOverride=None,
                    output_prefix="chatgpt",
                    max_tokens=5000,
                    promptOverrides=None):
        self.output_prefix = output_prefix
        self.prompt_config = prompt_config
        print("prompt_config: " + str(self.prompt_config))
        if promptOverrides is not None:
            print("promptOverrides: " + str(promptOverrides))
            self.prompt_config.update(promptOverrides)
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
        if userMessage is None:
            file = open(userMessageFile, "r")
            self.userMessage = file.read()
            file.close()
        else:
            self.userMessage = userMessage

    # return dict for the model provider config and always default to openai
    def return_model_provider_config(self):
        model_provider = self.prompt_config.get("model_provider")
        if model_provider == "google":
            return {
                "base_url": f"https://generativelanguage.googleapis.com/v1beta/openai",
                "api_key": os.environ.get("GEMINI_API_KEY"),
            }
        else:
            return {
                "base_url": f"https://api.openai.com/v1",
                "api_key": os.environ.get("OPENAI_API_KEY"),
            }
    # return a string with a list of all the days of the current week based on the provided date string
    def return_weekdays_from_date(self, date_string):
        week_days = []
        date = datetime.strptime(date_string, '%Y-%m-%d')
        weekStart = date - timedelta(days=date.weekday())
        for i in range(7):
            weekday = (weekStart + timedelta(days=i)).strftime("%A")
            day = (weekStart + timedelta(days=i)).strftime("%Y-%m-%d")
            week_days.append(f"{weekday}({day})")
        return f"{', '.join(week_days)}"
        
    def return_default_substitutions(self):
        return {
            "MC_JSON_SCHEMA": self.prompt_config["jsonSchema"],
            "MC_TODAY": self.weekStart.strftime("%Y-%m-%d"),
            "MC_WEEKSTART": self.weekStart.strftime("%G-W%V")
        }
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
        # if output_prefix is not empty, use it as prefix else use a combination of the model provider and the model
        if self.output_prefix:
            prefix = self.output_prefix
        else:
            prefix = self.prompt_config["model_provider"] + "_" + self.prompt_config["visionModel"]
        out = open(f"{prefix}_usage.json", "w")
        out.write(json.dumps(chat_completion.usage.to_dict(), indent=4, sort_keys=True))
        out.close()
        # print the chat completion for debugging
        print(chat_completion.choices[0].message.content)
        out = open(f"{prefix}.json", "w")
        out.write(self.extract_json_content(chat_completion.choices[0].message.content))
        out.close()

    def returnPromptAddonMessages(self):
        gpt_messages = []
        weekdaysExplicit = ""
        if self.prompt_config["addCurrentWeekdays"]:
            weekdaysExplicit = " containing the days " + self.return_weekdays_from_date(self.weekStart.strftime("%Y-%m-%d"))
        if self.prompt_config["addCurrentDate"]:
            gpt_messages.append({"role": "user", "content": """When you determine the calendar period from the input take your time to conclude if the period is reasonable as today is "Monday" {MC_TODAY} and calendar week {MC_WEEKSTART}{weekdaysExplicit}. You may need to reconsider if you determine a calendar week from the very past. Otherwise the period most likely will be for the current week or a few weeks in the future from today.""".format(**self.return_default_substitutions(),weekdaysExplicit=weekdaysExplicit)})
        return gpt_messages

    def processImageAndWriteToFile(self):

        client = OpenAI(**self.return_model_provider_config())
        systemPromptSubstituted = self.prompt_config["systemPrompt"].format(**self.return_default_substitutions())
        print("Using the prompt: " + systemPromptSubstituted)
        gpt_messages=[
            {"role": "system", "content": systemPromptSubstituted}]
        prompt_addon_messages = self.returnPromptAddonMessages()
        if prompt_addon_messages:
            gpt_messages.extend(prompt_addon_messages)
        print("gpt_messages: " + str(gpt_messages))
        gpt_messages.append({"role": "user", "content": [
            {
                "type": "text",
                "text": self.userMessagePrefix + self.userMessage
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": self.encode_image_and_return_string(self.userImageFile)
                }
            }
        ]})
        
        print(f"sending additional user msg: {self.userMessagePrefix + self.userMessage}")
        chat_completion = client.chat.completions.create(model=self.prompt_config["visionModel"],
                                                        messages=gpt_messages,
                                                        max_tokens=self.max_tokens)#,
                                                        #response_format={ "type":"json_object" })
        self.writeToFile(chat_completion)

    def processAndWriteToFile(self):
        client = OpenAI(**self.return_model_provider_config())
        systemPromptSubstituted = self.prompt_config["systemPrompt"].format(**self.return_default_substitutions())
        # print the system prompt for debugging
        gpt_messages=[
            {"role": "system", "content": systemPromptSubstituted}]
        prompt_addon_messages = self.returnPromptAddonMessages()
        if prompt_addon_messages:
            gpt_messages.extend(prompt_addon_messages)
        gpt_messages.append(
            {"role": "user", "content": self.userMessagePrefix + self.userMessage})
        print("gpt_messages: " + str(gpt_messages))
        chat_completion = client.chat.completions.create(model="gpt-5-mini",
                                                        messages=gpt_messages,
                                                        response_format={ "type":"text" },
                                                        seed=1,
                                                        max_completion_tokens=self.max_tokens)
        self.writeToFile(chat_completion)
