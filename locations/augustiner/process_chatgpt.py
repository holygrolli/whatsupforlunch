import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../.shared')
from DefaultMealChat import DefaultMealChat

# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat(systemPromptFile=sys.argv[1], 
                userMessageFile=sys.argv[2], 
                userMessagePrefix="The input is:\n")

meal_chat.processAndWriteToFile()
