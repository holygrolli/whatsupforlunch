import os, sys, inspect
sys.path.append(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) + '/../.shared')
from DefaultMealChat import DefaultMealChat
from config import config

# Create an instance of DefaultMealChat
meal_chat = DefaultMealChat(
              **config
            )

meal_chat.processAndWriteToFile()