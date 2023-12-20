import openai, sys

class DefaultMealChat:
    def __init__(self, 
                    systemPrompt=None, 
                    systemPromptFile="chatgpt_systemprompt.txt", 
                    userMessage=None, 
                    userMessageFile="chatgpt_user.txt",
                    userMessagePrefix=""):
        self.userMessagePrefix = userMessagePrefix
        if systemPrompt is None:
            file = open(systemPromptFile, "r")
            self.systemPrompt = file.read()
            file.close()
        else:
            self.systemPrompt = systemPrompt
        if userMessage is None:
            file = open(userMessageFile, "r")
            self.userMessage = file.read()
            file.close()
        else:
            self.userMessage = userMessage

    def processAndWriteToFile(self):
        # print the system prompt for debugging
        print("Using the prompt: " + self.systemPrompt)
        gpt_messages=[
            {"role": "system", "content": self.systemPrompt},
            {"role": "user", "content": self.userMessagePrefix + self.userMessage}]
        print("gpt_messages: " + str(gpt_messages))
        chat_completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=gpt_messages)
        print(chat_completion.usage)
        # print the chat completion for debugging
        print(chat_completion.choices[0].message.content)
        out = open ("chatgpt.json", "w")
        out.write(chat_completion.choices[0].message.content)
        out.close()