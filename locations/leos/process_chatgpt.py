from datetime import datetime, timedelta
import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../.shared')
from DefaultMealChat import DefaultMealChat

today = datetime.today()
weekStart = today - timedelta(days=today.weekday())
print(weekStart.strftime('%Y-%m-%d'))

# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat(systemPromptFile=sys.argv[1], 
                userMessageFile=sys.argv[2], 
                userMessagePrefix="assume today is " + weekStart.strftime('%Y-%m-%d') + " and the input is:\n")

meal_chat.processAndWriteToFile()
# create a chat completion
chat_completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[
    {"role": "system", "content": prompt},
    {"role": "user", "content": "assume today is " + weekStart.strftime('%Y-%m-%d') + " and the input is:\n" + inputString}])
