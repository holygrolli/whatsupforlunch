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
                userMessagePrefix="You will infer the meal offers from the following German headline text, expecting the first date being of year " + datetime.today().strftime('%Y') + ": " + dateInput + "Parse the meals of following CSV data:\n")

meal_chat.processAndWriteToFile()