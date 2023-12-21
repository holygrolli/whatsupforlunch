from datetime import datetime, timedelta
import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../.shared')
from DefaultMealChat import DefaultMealChat

today = datetime.today()
weekStart = today - timedelta(days=today.weekday())
# if on weekend assume we are running for next week
if today.weekday()>4:
    weekStart = weekStart + timedelta(days=7)
print(weekStart.strftime('%Y-%m-%d'))

# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat(systemPromptFile=sys.argv[1], 
                userMessageFile=sys.argv[2], 
                userMessagePrefix="The week starts with \"Montag\" " + weekStart.strftime('%Y-%m-%d') + " and the input is:\n")

meal_chat.processAndWriteToFile()
