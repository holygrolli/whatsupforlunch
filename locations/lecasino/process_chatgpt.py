from datetime import datetime
import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../.shared')
from DefaultMealChat import DefaultMealChat

ftxt = open("output.txt", "r")
dateInput = ftxt.read()
ftxt.close()
# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat(systemPromptFile=sys.argv[1], 
                userMessageFile=sys.argv[2], 
                userMessagePrefix="The current week of year " + datetime.today().strftime('%Y') + " is defined as by this German text: " + dateInput + "\nThe CSV data is:\n")

meal_chat.processAndWriteToFile()