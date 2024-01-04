import openai, sys
from datetime import datetime, timedelta

class DefaultMealChat:
    def __init__(self, 
                    systemPrompt=None, 
                    systemPromptFile="chatgpt_systemprompt.txt", 
                    userMessage=None, 
                    userMessageFile="chatgpt_user.txt",
                    userMessagePrefix="",
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


    def writeToFile(self, chat_completion):
        print(chat_completion.usage)
        out = open ("usage.json", "w")
        out.write(str(chat_completion.usage))
        out.close()
        # print the chat completion for debugging
        print(chat_completion.choices[0].message.content)
        out = open ("chatgpt.json", "w")
        out.write(chat_completion.choices[0].message.content)
        out.close()

    def processImageAndWriteToFile(self, userImage=""):
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
                "image_url": userImage
            }
        ]})
        
        #print("gpt_messages: " + str(gpt_messages))
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
